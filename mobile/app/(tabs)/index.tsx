import { useState, useEffect, useRef } from 'react';
import { Text, View, Button, Platform, StyleSheet, ScrollView } from 'react-native';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

export default function HomeScreen() {
  const [expoPushToken, setExpoPushToken] = useState('');
  const [notification, setNotification] = useState(false);
  const notificationListener = useRef();
  const responseListener = useRef();
  const [signals, setSignals] = useState([]);

  useEffect(() => {
    registerForPushNotificationsAsync().then(token => setExpoPushToken(token));

    notificationListener.current = Notifications.addNotificationReceivedListener(notification => {
      setNotification(notification);
      // Add to list
      const content = notification.request.content;
      setSignals(prev => [{ title: content.title, body: content.body, date: new Date().toLocaleTimeString() }, ...prev]);
    });

    responseListener.current = Notifications.addNotificationResponseReceivedListener(response => {
      console.log(response);
    });

    return () => {
      Notifications.removeNotificationSubscription(notificationListener.current);
      Notifications.removeNotificationSubscription(responseListener.current);
    };
  }, []);

  return (
    <View style={styles.container}>
      <Text style={styles.header}>NotifyInvest</Text>

      {/* Token hidden for production aesthetics. Check console logs if needed. */}

      <View style={styles.feed}>
        <Text style={styles.feedHeader}>Recent Signals:</Text>
        <ScrollView>
          {signals.length === 0 && <Text style={styles.empty}>No signals yet. Waiting for news...</Text>}
          {signals.map((sig, index) => (
            <View key={index} style={styles.card}>
              <Text style={styles.cardTitle}>{sig.title}</Text>
              <Text style={styles.cardBody}>{sig.body}</Text>
              <Text style={styles.cardDate}>{sig.date}</Text>
            </View>
          ))}
        </ScrollView>
      </View>
    </View>
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

  // Bypass Device.isDevice check to allow Emulators/Web for testing
  // if (Device.isDevice) { ... }

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
      // Handle Web/VAPID error gracefully
      const errorString = `${e}`;
      if (errorString.includes('vapidPublicKey')) {
        console.warn("Web Push requires VAPID keys. Using Mock Token.");
        token = "WEB_MOCK_TOKEN_" + Math.random().toString(36).substring(7);
      }
      // Handle missing Project ID (Emulator/Bare)
      else if (errorString.includes('projectId')) {
        console.warn("No Project ID found. Using Emulator Mock Token.");
        token = "EMULATOR_MOCK_TOKEN_" + Math.random().toString(36).substring(7);
      }
      else {
        token = `Error: ${e}`;
        console.error(e);
      }
    }
  } else {
    alert('Must use physical device for Push Notifications');
  }

  // --- V2: Register Token with Cloud API ---
  if (token && !token.startsWith('Error')) {
    try {
      console.log("Registering token with Cloud API...");
      const SERVER_URL = 'http://144.22.206.150:5000/register'; // YOUR_VM_IP
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
      // Optional: Retry logic could go here
    }
  }

  return token;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
    paddingTop: 50,
    paddingHorizontal: 20,
  },
  header: {
    fontSize: 28,
    fontWeight: 'bold',
    marginBottom: 20,
    color: '#333',
    textAlign: 'center',
  },

  feed: {
    flex: 1,
    style: { flex: 1 } /* Fixed flex style for feed container */
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
    borderLeftColor: '#4CAF50', // Green for signal
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
  }
});
