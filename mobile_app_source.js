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

export default function App() {
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
            <Text style={styles.header}>B3 Signals</Text>

            <View style={styles.tokenContainer}>
                <Text style={styles.label}>Your Push Token:</Text>
                <Text selectable style={styles.token}>{expoPushToken}</Text>
                <Text style={styles.hint}>(Copy this to backend/token.txt)</Text>
            </View>

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

    if (Device.isDevice) {
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
        // Learn more about projectId:
        // https://docs.expo.dev/push-notifications/push-notifications-setup/#configure-projectid
        try {
            const projectId =
                Constants?.expoConfig?.extra?.eas?.projectId ?? Constants?.easConfig?.projectId;
            if (!projectId) {
                // locally usually works without ID in Expo Go
            }
            token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
            console.log("Token:", token);
        } catch (e) {
            token = `${e}`;
        }
    } else {
        alert('Must use physical device for Push Notifications');
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
    tokenContainer: {
        backgroundColor: '#fff',
        padding: 15,
        borderRadius: 10,
        marginBottom: 20,
        elevation: 2,
    },
    label: {
        fontSize: 14,
        color: '#666',
        marginBottom: 5,
    },
    token: {
        fontSize: 12,
        color: '#007AFF',
        fontFamily: 'monospace',
    },
    hint: {
        fontSize: 10,
        color: '#999',
        marginTop: 5,
        fontStyle: 'italic',
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
