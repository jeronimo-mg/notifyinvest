import { useState, useEffect, useRef } from 'react';
import { Text, View, Platform, StyleSheet, ScrollView, Linking, TouchableOpacity, TextInput, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';

const SERVER_IP = '144.22.206.150'; // OCI VM IP

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

interface SignalEvaluation {
  status: 'CONSOLIDATED' | 'PARTIAL' | 'REVERSED' | 'EXPIRED_MISSED' | 'TRACKING' | 'TRACKING_ADVERSE' | string;
  status_label?: string;
  status_badge?: string;
  consolidated?: boolean;
  trading_time_to_consolidate_str?: string;
  entry_price?: number;
  latest_price?: number;
  latest_change_pct?: number;
  max_favorable_pct?: number;
  max_adverse_pct?: number;
  target_threshold_pct?: number;
  verdict?: string;
  scores?: {
    signal: number;
    impact: number;
    sentiment: number;
    reason: number;
    overall: number;
  };
}

interface Signal {
  id?: string;
  title: string | null;
  body: string | null;
  date: string;
  url?: string;
  data?: {
    url?: string;
    source_type?: string;
    source_name?: string;
  };
  evaluation?: SignalEvaluation;
}

export default function HomeScreen() {
  const [expoPushToken, setExpoPushToken] = useState<string | undefined>('');
  const [notification, setNotification] = useState<Notifications.Notification | false>(false);
  const notificationListener = useRef<Notifications.Subscription>(undefined);
  const responseListener = useRef<Notifications.Subscription>(undefined);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [expandedEvalIndex, setExpandedEvalIndex] = useState<number | null>(null);

  // Filters
  const [filterType, setFilterType] = useState<'ALL' | 'BUY' | 'SELL'>('ALL');
  const [minImpact, setMinImpact] = useState('');

  const syncSignals = async (query = '') => {
    try {
      console.log(`Syncing signals (query="${query}")...`);
      const url = `http://${SERVER_IP}:5000/signals?limit=50&search=${encodeURIComponent(query)}`;
      const response = await fetch(url);
      const data = await response.json();
      console.log('History received:', data?.length);

      if (Array.isArray(data)) {
        setSignals(prev => {
          const newSignals: Signal[] = data.map((item: any) => ({
            id: item.id,
            title: item.title,
            body: item.body,
            // Timestamp is numeric seconds in history.json
            date: new Date(item.timestamp * 1000).toLocaleTimeString(),
            url: item.data?.url,
            data: item.data,
            evaluation: item.evaluation
          }));

          // History comes oldest-first (append), we want newest-first in UI
          return newSignals.reverse();
        });
      }
    } catch (e) {
      console.error('Failed to sync signals:', e);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await syncSignals(searchQuery);
    setRefreshing(false);
  };

  // derived state for filtering
  const filteredSignals = signals.filter(sig => {
    // 1. Type Filter
    if (filterType !== 'ALL') {
      if (!sig.title?.toUpperCase().includes(filterType)) return false;
    }

    // 2. Impact Filter
    if (minImpact) {
      const impactVal = parseInt(minImpact);
      if (!isNaN(impactVal) && sig.body) {
        // Regex to find "Estimativa: +5%" or "Estimativa: 5%"
        // We look for digits followed by %
        const match = sig.body.match(/(\d+)%/);
        if (match) {
          const currentImpact = parseInt(match[1]);
          if (currentImpact < impactVal) return false;
        }
      }
    }
    return true;
  });

  useEffect(() => {
    // 1. Sync Inbox immediately
    syncSignals();

    // 2. Register for Pushes
    registerForPushNotificationsAsync().then(token => setExpoPushToken(token));

    notificationListener.current = Notifications.addNotificationReceivedListener(notification => {
      setNotification(notification);
      // Add to list with URL
      const content = notification.request.content;
      const url = content.data?.url as string | undefined;
      setSignals(prev => [{
        title: content.title,
        body: content.body,
        date: new Date().toLocaleTimeString(),
        url: url
      }, ...prev]);
    });

    responseListener.current = Notifications.addNotificationResponseReceivedListener(response => {
      console.log('Notification clicked, opening app.');
    });

    return () => {
      notificationListener.current && notificationListener.current.remove();
      responseListener.current && responseListener.current.remove();
    };
  }, []);

  useEffect(() => {
    const delayDebounceFn = setTimeout(() => {
      syncSignals(searchQuery);
    }, 500);

    return () => clearTimeout(delayDebounceFn);
  }, [searchQuery]);

  return (
    <SafeAreaView style={styles.container}>
      <Text style={styles.header}>NotifyInvest</Text>

      <View style={styles.searchContainer}>
        <TextInput
          style={styles.searchInput}
          placeholder="🔎 Pesquisar (ex: PETR4)..."
          value={searchQuery}
          onChangeText={text => setSearchQuery(text)}
          onSubmitEditing={() => syncSignals(searchQuery)}
          returnKeyType="search"
        />
      </View>

      {/* Filter Controls */}
      <View style={styles.filters}>
        <View style={styles.typeButtons}>
          <TouchableOpacity onPress={() => setFilterType('ALL')} style={[styles.filterBtn, filterType === 'ALL' && styles.filterBtnActive]}>
            <Text style={[styles.filterBtnText, filterType === 'ALL' && styles.filterBtnTextActive]}>Todos</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setFilterType('BUY')} style={[styles.filterBtn, filterType === 'BUY' && styles.filterBtnActive, { borderColor: '#4CAF50' }]}>
            <Text style={[styles.filterBtnText, filterType === 'BUY' && styles.filterBtnTextActive, { color: filterType === 'BUY' ? '#fff' : '#4CAF50' }]}>Buy</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setFilterType('SELL')} style={[styles.filterBtn, filterType === 'SELL' && styles.filterBtnActive, { borderColor: '#F44336' }]}>
            <Text style={[styles.filterBtnText, filterType === 'SELL' && styles.filterBtnTextActive, { color: filterType === 'SELL' ? '#fff' : '#F44336' }]}>Sell</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.impactInputContainer}>
          <Text style={{ fontSize: 12, color: '#666', marginRight: 5 }}>% Mín:</Text>
          <TextInput
            style={styles.impactInput}
            placeholder="0"
            keyboardType="numeric"
            value={minImpact}
            onChangeText={setMinImpact}
          />
        </View>
      </View>

      <View style={styles.feed}>

        <ScrollView
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
          }
        >
          {filteredSignals.length === 0 && <Text style={styles.empty}>Nenhum sinal encontrado.</Text>}
          {filteredSignals.map((sig, index) => {
            const sourceType = sig.data?.source_type || 'FATO';
            let badgeColor = '#E3F2FD';
            let badgeTextColor = '#1565C0';
            if (sourceType === 'INTERPRETACAO') { badgeColor = '#FFF3E0'; badgeTextColor = '#E65100'; }
            else if (sourceType === 'PERCEPCAO') { badgeColor = '#FCE4EC'; badgeTextColor = '#C2185B'; }

            const ev = sig.evaluation;
            let evalBg = '#FFF8E1';
            let evalBorder = '#FFE082';
            let evalText = '#E65100';
            let evalLabel = ev?.status_badge || '⏳ Em Observação';

            if (ev) {
              if (ev.status === 'CONSOLIDATED') {
                evalBg = '#E8F5E9';
                evalBorder = '#A5D6A7';
                evalText = '#1B5E20';
              } else if (ev.status === 'PARTIAL') {
                evalBg = '#E3F2FD';
                evalBorder = '#90CAF9';
                evalText = '#0D47A1';
              } else if (ev.status === 'REVERSED' || ev.status === 'TRACKING_ADVERSE') {
                evalBg = '#FFEBEE';
                evalBorder = '#EF9A9A';
                evalText = '#B71C1C';
              } else if (ev.status === 'EXPIRED_MISSED') {
                evalBg = '#F5F5F5';
                evalBorder = '#BDBDBD';
                evalText = '#616161';
              }
            }

            const isExpanded = expandedEvalIndex === index;

            return (
              <TouchableOpacity
                key={index}
                style={[styles.card, sig.title?.includes('SELL') ? { borderLeftColor: '#F44336' } : { borderLeftColor: '#4CAF50' }]}
                onPress={() => sig.url && Linking.openURL(sig.url)}
              >
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
                  <Text style={styles.cardTitle}>{sig.title}</Text>
                  <View style={{ backgroundColor: badgeColor, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                    <Text style={{ color: badgeTextColor, fontSize: 10, fontWeight: 'bold' }}>{sourceType}</Text>
                  </View>
                </View>

                {/* Evaluation Status Badge */}
                {ev && (
                  <TouchableOpacity
                    onPress={() => setExpandedEvalIndex(isExpanded ? null : index)}
                    style={{
                      backgroundColor: evalBg,
                      borderColor: evalBorder,
                      borderWidth: 1,
                      paddingHorizontal: 8,
                      paddingVertical: 4,
                      borderRadius: 6,
                      marginBottom: 8,
                      flexDirection: 'row',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                  >
                    <Text style={{ color: evalText, fontSize: 11, fontWeight: 'bold' }}>
                      {evalLabel}
                      {ev.scores?.overall !== undefined ? ` • Nota: ${ev.scores.overall}/100` : ''}
                    </Text>
                    <Text style={{ color: evalText, fontSize: 10, fontWeight: '600' }}>
                      {isExpanded ? '▲ Ocultar' : '▼ Ver Auditoria'}
                    </Text>
                  </TouchableOpacity>
                )}

                <Text style={styles.cardBody}>{sig.body}</Text>

                {/* Expandable Evaluation Details Panel */}
                {ev && isExpanded && (
                  <View style={{ backgroundColor: '#F8FAFC', borderColor: '#E2E8F0', borderWidth: 1, borderRadius: 8, padding: 10, marginTop: 10 }}>
                    {ev.entry_price !== undefined && ev.latest_price !== undefined && (
                      <Text style={{ fontSize: 12, color: '#333', marginBottom: 4 }}>
                        📈 <Text style={{ fontWeight: 'bold' }}>B3:</Text> R$ {ev.entry_price.toFixed(2)} → R$ {ev.latest_price.toFixed(2)} ({ev.latest_change_pct && ev.latest_change_pct >= 0 ? '+' : ''}{ev.latest_change_pct ?? 0}%)
                        {'  '}| Pico a favor: <Text style={{ fontWeight: 'bold', color: '#2E7D32' }}>{ev.max_favorable_pct && ev.max_favorable_pct >= 0 ? '+' : ''}{ev.max_favorable_pct ?? 0}%</Text>
                      </Text>
                    )}
                    {ev.consolidated && ev.trading_time_to_consolidate_str && (
                      <Text style={{ fontSize: 12, color: '#1B5E20', fontWeight: '600', marginBottom: 4 }}>
                        ⏱️ Consolidou (≥70% da meta) em {ev.trading_time_to_consolidate_str} de pregão
                      </Text>
                    )}
                    {ev.scores && (
                      <Text style={{ fontSize: 11, color: '#555', marginBottom: 4 }}>
                        🎯 <Text style={{ fontWeight: 'bold' }}>Acerto:</Text> Signal {ev.scores.signal}% • Impact {ev.scores.impact}% • Sentiment {ev.scores.sentiment}% • Reason {ev.scores.reason}%
                      </Text>
                    )}
                    {ev.verdict && (
                      <Text style={{ fontSize: 11, color: '#444', fontStyle: 'italic' }}>
                        💬 {ev.verdict}
                      </Text>
                    )}
                  </View>
                )}

                {sig.url && (
                  <View style={{ backgroundColor: '#eee', padding: 8, borderRadius: 6, marginTop: 10, alignSelf: 'flex-start' }}>
                    <Text style={{ fontWeight: '500', color: '#333' }}>
                      🔗 Fonte: {sig.data && sig.data.source_name ? sig.data.source_name : 'Abrir Link'}
                    </Text>
                  </View>
                )}
                <Text style={styles.cardDate}>{sig.date}</Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>
    </SafeAreaView>
  );
}

async function registerForPushNotificationsAsync() {
  let token;

  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('default', {
      name: 'default',
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: '#FF231F7C',
    });
  }

  if (true) {
    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;
    if (existingStatus !== 'granted') {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }
    if (finalStatus !== 'granted') {
      alert('Failed to get push token for push notification!');
      return;
    }

    try {
      const projectId =
        Constants?.expoConfig?.extra?.eas?.projectId ?? Constants?.easConfig?.projectId;

      token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
      console.log("Token:", token);
    } catch (e) {
      token = `${e}`;
      console.error(e);
    }
  } else {
    alert('Must use physical device for Push Notifications');
  }

  // --- Register Token with Cloud API ---
  if (token && !token.startsWith('Error')) {
    try {
      console.log("Registering token with Cloud API...");
      const SERVER_URL = `http://${SERVER_IP}:5000/register`;
      await fetch(SERVER_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ token: token }),
      });
      console.log("Token registered successfully on Cloud!");
    } catch (apiError) {
      console.error("Failed to register token on Cloud:", apiError);
    }
  }

  return token;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
    paddingHorizontal: 20,
  },
  header: {
    fontSize: 28,
    fontWeight: 'bold',
    marginBottom: 10, // reduced margin
    marginTop: 10,
    color: '#333',
    textAlign: 'center',
  },
  searchContainer: {
    paddingBottom: 10,
  },
  searchInput: {
    backgroundColor: '#fff',
    padding: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#ddd',
    fontSize: 16,
  },
  feed: {
    flex: 1,
  },
  feedHeader: {
    fontSize: 20,
    fontWeight: '600',
    marginBottom: 10,
    color: '#444',
  },
  empty: {
    textAlign: 'center',
    color: '#999',
    marginTop: 50,
  },
  card: {
    backgroundColor: '#fff',
    padding: 15,
    borderRadius: 10,
    marginBottom: 10,
    borderLeftWidth: 5,
    borderLeftColor: '#4CAF50',
    elevation: 2,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    marginBottom: 5,
  },
  cardBody: {
    fontSize: 14,
    color: '#444',
  },
  cardDate: {
    fontSize: 10,
    color: '#aaa',
    marginTop: 5,
    textAlign: 'right',
  },
  linkText: {
    fontWeight: 'bold',
    fontSize: 14,
  },
  filters: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },
  typeButtons: {
    flexDirection: 'row',
    gap: 5,
  },
  filterBtn: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: '#888',
    backgroundColor: 'transparent',
  },
  filterBtnActive: {
    backgroundColor: '#333',
    borderColor: '#333',
  },
  filterBtnText: {
    fontSize: 12,
    color: '#333',
    fontWeight: '600',
  },
  filterBtnTextActive: {
    color: '#fff',
  },
  impactInputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  impactInput: {
    backgroundColor: '#fff',
    paddingVertical: 5,
    paddingHorizontal: 10,
    borderRadius: 5,
    borderWidth: 1,
    borderColor: '#ddd',
    width: 50,
    textAlign: 'center',
  }
});
