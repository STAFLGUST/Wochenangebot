import { Redirect } from 'expo-router';
import { useSitzung } from '../zustand/sitzung';

export default function Start() {
  const { rolle } = useSitzung();
  return <Redirect href={rolle === 'team' ? '/vorgaenge' : '/angebot'} />;
}
