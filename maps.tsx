
import { useEffect, useRef, useState } from 'react';

declare global { interface Window { google:any } }

export default function Maps(){
  const mapRef = useRef<HTMLDivElement>(null);
  const [hours, setHours] = useState(168);

  useEffect(()=>{
    const key = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY || '';
    const script = document.createElement('script');
    script.src = `https://maps.googleapis.com/maps/api/js?key=${key}&libraries=visualization`;
    script.async = true;
    script.onload = () => initMap();
    document.body.appendChild(script);
    async function initMap(){
      const center = { lat: 39.8283, lng: -98.5795 }; // USA
      const map = new window.google.maps.Map(mapRef.current!, { zoom: 4, center, mapTypeControl: false });
      await drawHeat(map, hours);
      // Watch for changes
      const sel = document.getElementById('hours') as HTMLSelectElement;
      sel.addEventListener('change', async () => {
        const h = Number(sel.value);
        setHours(h);
        await drawHeat(map, h);
      });
    }
    async function drawHeat(map:any, h:number){
      const res = await fetch(`http://localhost:3000/v1/location/public-hotspots?hours=${h}`);
      const data = await res.json();
      const points = data.items.map((i:any)=>({ location: new window.google.maps.LatLng(i.lat, i.lng), weight: i.weight }));
      const layer = new window.google.maps.visualization.HeatmapLayer({ data: points, radius: 30 });
      layer.setMap(null); layer.setMap(map);
    }
  },[]);

  return (
    <main style={{padding:0, margin:0}}>
      <div style={{position:'absolute', zIndex:10, top:12, left:12, background:'#fff', padding:8, borderRadius:8}}>
        <label>Timeframe: <select id="hours" defaultValue="168">
          <option value="24">Last 24h</option>
          <option value="168">Last 7d</option>
          <option value="720">Last 30d</option>
        </select></label>
      </div>
      <div ref={mapRef} style={{width:'100%', height:'100vh'}} />
    </main>
  );
}
