import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { StatusBar } from 'expo-status-bar';
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Account, HOME, loadTokens, Me } from './src/api';
import type { Stack as S } from './src/nav';
import { CaptureGuide, Capture, Processing, Review } from './src/screens/capture';
import { Home, Settings } from './src/screens/home';
import { Allergies, Concerns, CurrentRoutine, Health, Lifestyle, Urgent } from './src/screens/intake';
import { AuthScreen, BoundaryScreen, ConsentScreen, ProfileScreen, Welcome } from './src/screens/onboarding';
import { Referral, Results, Routine, Summary } from './src/screens/results';
import { AdminAudit, AdminCatalog, AdminHome, AdminModels, AdminRules, AdminUsers } from './src/screens/admin';
import { DermCase, DermQueue, DermRules, DermStats } from './src/screens/derm';
import { StaffCase, StaffInbox } from './src/screens/staff';
import { C } from './src/ui';

const Stack = createNativeStackNavigator<S>();

export default function App() {
  const [initial, setInitial] = useState<keyof S | null>(null);

  useEffect(() => {
    (async () => {
      const t = await loadTokens();
      if (!t) return setInitial('Welcome');
      try {
        // Each role opens on its own home screen.
        const me = await Account.me();
        if (me.role !== 'patient') return setInitial(HOME[me.role]);
        setInitial((await Me.profile()) ? 'Home' : 'Profile');
      } catch {
        setInitial('Welcome');
      }
    })();
  }, []);

  if (!initial) {
    return <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: C.bg }}><ActivityIndicator color={C.primary} /></View>;
  }

  return (
    <SafeAreaProvider>
      <NavigationContainer>
        <StatusBar style="dark" />
        <Stack.Navigator initialRouteName={initial}
          screenOptions={{ headerTintColor: C.primary, headerStyle: { backgroundColor: C.bg }, headerShadowVisible: false, title: '', contentStyle: { backgroundColor: C.bg } }}>
          <Stack.Screen name="Welcome" component={Welcome} options={{ headerShown: false }} />
          <Stack.Screen name="Boundary" component={BoundaryScreen} />
          <Stack.Screen name="Auth" component={AuthScreen} />
          <Stack.Screen name="Consent" component={ConsentScreen} />
          <Stack.Screen name="Profile" component={ProfileScreen} />
          <Stack.Screen name="Home" component={Home} />
          <Stack.Screen name="Concerns" component={Concerns} />
          <Stack.Screen name="Health" component={Health} />
          <Stack.Screen name="Urgent" component={Urgent} options={{ presentation: 'modal' }} />
          <Stack.Screen name="Allergies" component={Allergies} />
          <Stack.Screen name="CurrentRoutine" component={CurrentRoutine} />
          <Stack.Screen name="Lifestyle" component={Lifestyle} />
          <Stack.Screen name="CaptureGuide" component={CaptureGuide} />
          <Stack.Screen name="Capture" component={Capture} />
          <Stack.Screen name="Review" component={Review} />
          <Stack.Screen name="Processing" component={Processing} options={{ headerBackVisible: false, gestureEnabled: false }} />
          <Stack.Screen name="Results" component={Results} options={{ headerBackVisible: true }} />
          <Stack.Screen name="Routine" component={Routine} />
          <Stack.Screen name="Referral" component={Referral} />
          <Stack.Screen name="Summary" component={Summary} />
          <Stack.Screen name="Settings" component={Settings} />
          <Stack.Screen name="StaffInbox" component={StaffInbox} options={{ title: 'ICONIC clinic' }} />
          <Stack.Screen name="StaffCase" component={StaffCase} />
          <Stack.Screen name="DermQueue" component={DermQueue} options={{ title: 'Dermatologist' }} />
          <Stack.Screen name="DermCase" component={DermCase} />
          <Stack.Screen name="DermRules" component={DermRules} />
          <Stack.Screen name="DermStats" component={DermStats} />
          <Stack.Screen name="AdminHome" component={AdminHome} options={{ title: 'DermaLens admin' }} />
          <Stack.Screen name="AdminUsers" component={AdminUsers} />
          <Stack.Screen name="AdminCatalog" component={AdminCatalog} />
          <Stack.Screen name="AdminRules" component={AdminRules} />
          <Stack.Screen name="AdminModels" component={AdminModels} />
          <Stack.Screen name="AdminAudit" component={AdminAudit} />
        </Stack.Navigator>
      </NavigationContainer>
    </SafeAreaProvider>
  );
}
