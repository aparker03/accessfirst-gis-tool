import React from 'react'
import ReactDOM from 'react-dom/client'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import App from './App.jsx'
import './styles.css'

mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_PUBLIC_TOKEN || ''

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
