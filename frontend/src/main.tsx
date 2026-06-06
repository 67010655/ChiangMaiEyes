import React from 'react';
import ReactDOM from 'react-dom/client';
import 'leaflet/dist/leaflet.css';
import './styles/global.css';
import { App } from './App';
import { PitchMode } from './pitch/PitchMode';

const isPitch =
  typeof window !== 'undefined' &&
  (window.location.pathname.startsWith('/pitch') || window.location.hash === '#pitch');

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>{isPitch ? <PitchMode /> : <App />}</React.StrictMode>,
);
