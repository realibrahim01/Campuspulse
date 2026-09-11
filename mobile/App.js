import React, { useState } from 'react';
import {
  SafeAreaView, ScrollView, View, Text, TextInput, TouchableOpacity,
  StyleSheet, ActivityIndicator, StatusBar,
} from 'react-native';
import { Picker } from '@react-native-picker/picker';
import { api, setCreds, getEmail } from './api';

export default function App() {
  const [authed, setAuthed] = useState(false);
  return authed ? <Home onSignOut={() => setAuthed(false)} /> : <Login onLogin={() => setAuthed(true)} />;
}

function Login({ onLogin }) {
  const [email, setEmail] = useState('student01@campus.edu');
  const [password, setPassword] = useState('campus123');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function signIn() {
    setBusy(true); setError('');
    setCreds(email.trim(), password);
    try { await api.categories(); onLogin(); }
    catch (e) { setError(e.message === 'Unauthorized' ? 'Wrong email or password.' : e.message); }
    finally { setBusy(false); }
  }

  return (
    <SafeAreaView style={s.screen}>
      <StatusBar barStyle="dark-content" />
      <View style={s.loginBox}>
        <Text style={s.brand}>CampusPulse</Text>
        <Text style={s.muted}>Report a campus problem in 30 seconds</Text>
        <Text style={s.label}>Email</Text>
        <TextInput style={s.input} value={email} onChangeText={setEmail} autoCapitalize="none" />
        <Text style={s.label}>Password</Text>
        <TextInput style={s.input} value={password} onChangeText={setPassword} secureTextEntry />
        {error ? <Text style={s.error}>{error}</Text> : null}
        <TouchableOpacity style={s.primaryBtn} onPress={signIn} disabled={busy}>
          <Text style={s.primaryBtnText}>{busy ? 'Signing in…' : 'Sign in'}</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

function Home({ onSignOut }) {
  const [cats, setCats] = useState([]);
  const [locs, setLocs] = useState([]);
  const [reports, setReports] = useState([]);
  const [text, setText] = useState('');
  const [categoryId, setCategoryId] = useState(null);
  const [locationId, setLocationId] = useState(null);
  const [sublocation, setSublocation] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  React.useEffect(() => {
    Promise.all([api.categories(), api.locations(), api.myReports()])
      .then(([c, l, r]) => { setCats(c); setLocs(l); setReports(r); setLoaded(true); })
      .catch((e) => setMsg('Load failed: ' + e.message));
  }, []);

  async function submit() {
    if (!text.trim() || !categoryId || !locationId) {
      setMsg('Add a description, category, and location.'); return;
    }
    setBusy(true); setMsg('');
    try {
      await api.submit({ text: text.trim(), categoryId, locationId,
        sublocation: sublocation.trim() || null });
      setText(''); setSublocation(''); setCategoryId(null); setLocationId(null);
      setReports(await api.myReports());
      setMsg('Reported. Thank you — you will be notified as it progresses.');
    } catch (e) { setMsg('Submit failed: ' + e.message); }
    finally { setBusy(false); }
  }

  if (!loaded) {
    return <SafeAreaView style={s.screen}><ActivityIndicator style={{ marginTop: 60 }} /></SafeAreaView>;
  }

  return (
    <SafeAreaView style={s.screen}>
      <StatusBar barStyle="dark-content" />
      <View style={s.topbar}>
        <Text style={s.brandSm}>CampusPulse</Text>
        <TouchableOpacity onPress={onSignOut}><Text style={s.link}>{getEmail()} · sign out</Text></TouchableOpacity>
      </View>
      <ScrollView contentContainerStyle={{ padding: 16 }}>
        <Text style={s.h2}>Report a problem</Text>

        <Text style={s.label}>What's wrong?</Text>
        <TextInput style={[s.input, s.multiline]} value={text} onChangeText={setText}
          placeholder="e.g. Water cooler on Lab 2F not working" multiline />

        <Text style={s.label}>Category</Text>
        <View style={s.pickerWrap}>
          <Picker selectedValue={categoryId} onValueChange={setCategoryId}>
            <Picker.Item label="Select category…" value={null} />
            {cats.map((c) => <Picker.Item key={c.id} label={c.label} value={c.id} />)}
          </Picker>
        </View>

        <Text style={s.label}>Location</Text>
        <View style={s.pickerWrap}>
          <Picker selectedValue={locationId} onValueChange={setLocationId}>
            <Picker.Item label="Select location…" value={null} />
            {locs.map((l) => <Picker.Item key={l.id} label={l.name} value={l.id} />)}
          </Picker>
        </View>

        <Text style={s.label}>Specific spot (optional)</Text>
        <TextInput style={s.input} value={sublocation} onChangeText={setSublocation}
          placeholder="e.g. Room 210, 2nd sink" />

        {msg ? <Text style={s.msg}>{msg}</Text> : null}
        <TouchableOpacity style={s.primaryBtn} onPress={submit} disabled={busy}>
          <Text style={s.primaryBtnText}>{busy ? 'Submitting…' : 'Submit report'}</Text>
        </TouchableOpacity>

        <Text style={[s.h2, { marginTop: 28 }]}>My reports ({reports.length})</Text>
        {reports.map((r) => (
          <View key={r.id} style={s.reportCard}>
            <Text style={s.reportText}>{r.text}</Text>
            <Text style={s.muted}>
              {r.caseId ? 'Grouped into a case' : 'Submitted · awaiting triage'}
              {'  ·  '}{new Date(r.createdAt).toLocaleDateString()}
            </Text>
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#f4f5f7' },
  loginBox: { margin: 20, marginTop: 80, backgroundColor: '#fff', borderRadius: 12, padding: 24,
    borderWidth: 1, borderColor: '#e2e5ea' },
  brand: { fontSize: 26, fontWeight: '800', color: '#1f2430' },
  brandSm: { fontSize: 18, fontWeight: '800', color: '#1f2430' },
  muted: { color: '#6b7280', fontSize: 13 },
  label: { marginTop: 14, marginBottom: 4, fontSize: 12, color: '#6b7280',
    textTransform: 'uppercase', letterSpacing: 0.4 },
  input: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#e2e5ea', borderRadius: 8,
    padding: 11, fontSize: 15 },
  multiline: { minHeight: 70, textAlignVertical: 'top' },
  pickerWrap: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#e2e5ea', borderRadius: 8 },
  primaryBtn: { marginTop: 18, backgroundColor: '#2563eb', borderRadius: 8, padding: 14, alignItems: 'center' },
  primaryBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  error: { color: '#dc2626', marginTop: 10 },
  msg: { color: '#2563eb', marginTop: 12 },
  topbar: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    padding: 14, backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e2e5ea' },
  link: { color: '#2563eb', fontSize: 13 },
  h2: { fontSize: 18, fontWeight: '700', color: '#1f2430', marginBottom: 6 },
  reportCard: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#e2e5ea', borderRadius: 8,
    padding: 12, marginTop: 10 },
  reportText: { fontSize: 14, marginBottom: 4, color: '#1f2430' },
});
