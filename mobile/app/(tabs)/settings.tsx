import { useState, useEffect } from 'react';
import { StyleSheet, TextInput, View, TouchableOpacity, Alert, ActivityIndicator, ScrollView, Text } from 'react-native';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';
import { Platform } from 'react-native';

import ParallaxScrollView from '@/components/parallax-scroll-view';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { IconSymbol } from '@/components/ui/icon-symbol';

const SERVER_IP = '144.22.206.150';

export default function SettingsScreen() {
  const [minBuy, setMinBuy] = useState('0');
  const [minSell, setMinSell] = useState('0');

  // Lists
  const [whitelist, setWhitelist] = useState<string[]>([]);
  const [blacklist, setBlacklist] = useState<string[]>([]);
  const [newTicker, setNewTicker] = useState('');

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  const getPushToken = async () => {
    const projectId =
      Constants?.expoConfig?.extra?.eas?.projectId ?? Constants?.easConfig?.projectId;
    try {
      const tokenData = await Notifications.getExpoPushTokenAsync({ projectId });
      return tokenData.data;
    } catch (e) {
      console.error("Failed to get token", e);
      return null;
    }
  };

  const loadSettings = async () => {
    setLoading(true);
    try {
      const token = await getPushToken();
      if (!token) {
        setLoading(false);
        return;
      }

      const res = await fetch(`http://${SERVER_IP}:5000/preferences?token=${encodeURIComponent(token)}`);
      if (res.ok) {
        const data = await res.json();
        setMinBuy(data.min_buy?.toString() || '0');
        setMinSell(data.min_sell?.toString() || '0');
        setWhitelist(data.whitelist || []);
        setBlacklist(data.blacklist || []);
      }
    } catch (e) {
      console.error("Failed to load settings", e);
      Alert.alert("Erro", "Falha ao carregar configurações.");
    } finally {
      setLoading(false);
    }
  };

  const saveSettings = async () => {
    setSaving(true);
    try {
      const token = await getPushToken();
      if (!token) {
        Alert.alert("Erro", "Token de notificação não encontrado.");
        setSaving(false);
        return;
      }

      const body = {
        token: token,
        min_buy: parseInt(minBuy) || 0,
        min_sell: parseInt(minSell) || 0,
        whitelist: whitelist,
        blacklist: blacklist
      };

      const res = await fetch(`http://${SERVER_IP}:5000/preferences`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });

      if (res.ok) {
        Alert.alert("Sucesso", "Configurações salvas!");
      } else {
        Alert.alert("Erro", "Falha ao salvar no servidor.");
      }
    } catch (e) {
      console.error(e);
      Alert.alert("Erro", "Erro de conexão.");
    } finally {
      setSaving(false);
    }
  };

  const addTicker = (listType: 'white' | 'black') => {
    if (!newTicker.trim()) return;
    const ticker = newTicker.trim().toUpperCase();

    if (listType === 'white') {
      if (!whitelist.includes(ticker)) setWhitelist([...whitelist, ticker]);
      // Remove from blacklist if present
      if (blacklist.includes(ticker)) setBlacklist(blacklist.filter(t => t !== ticker));
    } else {
      if (!blacklist.includes(ticker)) setBlacklist([...blacklist, ticker]);
      // Remove from whitelist if present
      if (whitelist.includes(ticker)) setWhitelist(whitelist.filter(t => t !== ticker));
    }
    setNewTicker('');
  };

  const removeTicker = (ticker: string, listType: 'white' | 'black') => {
    if (listType === 'white') {
      setWhitelist(whitelist.filter(t => t !== ticker));
    } else {
      setBlacklist(blacklist.filter(t => t !== ticker));
    }
  };

  return (
    <ParallaxScrollView
      headerBackgroundColor={{ light: '#D0D0D0', dark: '#353636' }}
      headerImage={
        <IconSymbol
          size={310}
          color="#808080"
          name="gearshape.fill"
          style={styles.headerImage}
        />
      }>
      <ThemedView style={styles.titleContainer}>
        <ThemedText type="title">Configurações</ThemedText>
      </ThemedView>

      <ThemedText>
        Controle granular das suas notificações.
      </ThemedText>

      {loading ? (
        <ActivityIndicator size="large" color="#2196F3" />
      ) : (
        <View style={styles.form}>

          {/* Thresholds Section */}
          <ThemedText type="defaultSemiBold" style={styles.sectionTitle}>💰 Limites de Preço</ThemedText>

          <View style={styles.inputGroup}>
            <ThemedText type="subtitle">Estimativa de alta mínima (%)</ThemedText>
            <ThemedText style={styles.helperText}>Notificar apenas se subir mais que:</ThemedText>
            <TextInput
              style={styles.input}
              value={minBuy}
              onChangeText={setMinBuy}
              keyboardType="numeric"
              placeholder="2%"
            />
          </View>
          <View style={styles.inputGroup}>
            <ThemedText type="subtitle">Estimativa de baixa mínima (%)</ThemedText>
            <ThemedText style={styles.helperText}>Notificar apenas se cair mais que:</ThemedText>
            <TextInput
              style={styles.input}
              value={minSell}
              onChangeText={setMinSell}
              keyboardType="numeric"
              placeholder="5%"
            />
          </View>

          {/* Companies Section */}
          <ThemedText type="defaultSemiBold" style={styles.sectionTitle}>🏢 Empresas (Tickers)</ThemedText>

          <View style={styles.addTickerRow}>
            <TextInput
              style={[styles.input, { flex: 1 }]}
              placeholder="Ex: PETR4"
              value={newTicker}
              onChangeText={t => setNewTicker(t.toUpperCase())}
              autoCapitalize="characters"
            />
          </View>
          <View style={styles.buttonRow}>
            <TouchableOpacity style={[styles.smallButton, styles.greenBtn]} onPress={() => addTicker('white')}>
              <Text style={styles.btnText}>+ Monitorar</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[styles.smallButton, styles.redBtn]} onPress={() => addTicker('black')}>
              <Text style={styles.btnText}>+ Ignorar</Text>
            </TouchableOpacity>
          </View>

          {/* Lists Display */}
          {whitelist.length > 0 && (
            <View>
              <ThemedText type="defaultSemiBold" style={{ color: '#4CAF50' }}>✅ Monitorando (Whitelist):</ThemedText>
              <ThemedText style={{ fontSize: 12, marginBottom: 5 }}>Você receberá notificações APENAS destas empresas.</ThemedText>
              <View style={styles.chipContainer}>
                {whitelist.map(t => (
                  <TouchableOpacity key={t} style={[styles.chip, { borderColor: '#4CAF50' }]} onPress={() => removeTicker(t, 'white')}>
                    <Text>{t} ✕</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          )}

          {blacklist.length > 0 && (
            <View>
              <ThemedText type="defaultSemiBold" style={{ color: '#F44336' }}>🚫 Ignorando (Blacklist):</ThemedText>
              <ThemedText style={{ fontSize: 12, marginBottom: 5 }}>Você NUNCA receberá notificações destas empresas.</ThemedText>
              <View style={styles.chipContainer}>
                {blacklist.map(t => (
                  <TouchableOpacity key={t} style={[styles.chip, { borderColor: '#F44336' }]} onPress={() => removeTicker(t, 'black')}>
                    <Text>{t} ✕</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          )}

          <TouchableOpacity style={styles.saveButton} onPress={saveSettings} disabled={saving}>
            <ThemedText style={styles.saveButtonText}>
              {saving ? "Salvando..." : "Salvar Tudo"}
            </ThemedText>
          </TouchableOpacity>

          <View style={styles.aboutSection}>
            <ThemedText type="defaultSemiBold" style={styles.sectionTitle}>ℹ️ Sobre o NotifyInvest</ThemedText>
            <ThemedText style={styles.aboutText}>
              O NotifyInvest utiliza Inteligência Artificial avançada para monitorar o mercado financeiro 24/7.
              Analisamos notícias em tempo real e filtramos o ruído para te entregar apenas os sinais que realmente importam para sua carteira.
            </ThemedText>
            <ThemedText style={styles.versionText}>Versão 1.0.0 (v9)</ThemedText>
          </View>
        </View>
      )}
    </ParallaxScrollView>
  );
}

const styles = StyleSheet.create({
  headerImage: {
    color: '#808080',
    bottom: -90,
    left: -35,
    position: 'absolute',
  },
  titleContainer: {
    flexDirection: 'row',
    gap: 8,
  },
  sectionTitle: {
    marginTop: 10,
    fontSize: 18,
    borderBottomWidth: 1,
    borderBottomColor: '#ccc',
    paddingBottom: 5,
  },
  form: {
    marginTop: 20,
    gap: 20,
    paddingBottom: 50,
  },
  row: {
    flexDirection: 'row',
    gap: 20,
  },
  inputGroup: {
    gap: 8,
    // flex: 1, // Removed flex: 1 since we are vertical now
  },
  helperText: {
    fontSize: 12,
    color: '#666',
  },
  input: {
    backgroundColor: '#fff',
    padding: 12,
    borderRadius: 8,
    fontSize: 16,
    borderWidth: 1,
    borderColor: '#ddd',
  },
  addTickerRow: {
    flexDirection: 'row',
    gap: 10,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 10,
  },
  smallButton: {
    padding: 10,
    borderRadius: 6,
    flex: 1,
    alignItems: 'center',
  },
  greenBtn: { backgroundColor: '#E8F5E9', borderWidth: 1, borderColor: '#4CAF50' },
  redBtn: { backgroundColor: '#FFEBEE', borderWidth: 1, borderColor: '#F44336' },
  btnText: { fontWeight: 'bold', fontSize: 12, color: '#333' },

  chipContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 5,
  },
  chip: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderRadius: 16,
    paddingVertical: 5,
    paddingHorizontal: 10,
  },
  saveButton: {
    backgroundColor: '#2196F3',
    padding: 16,
    borderRadius: 8,
    alignItems: 'center',
    marginTop: 20,
  },
  saveButtonText: {
    color: 'white',
    fontWeight: 'bold',
    fontSize: 16,
  },
  aboutSection: {
    marginTop: 30,
    borderTopWidth: 1,
    borderTopColor: '#ccc',
    paddingTop: 20,
  },
  aboutText: {
    fontSize: 14,
    color: '#555',
    marginTop: 10,
    lineHeight: 20,
  },
  versionText: {
    textAlign: 'center',
    color: '#999',
    fontSize: 12,
    marginTop: 20,
  }
});
