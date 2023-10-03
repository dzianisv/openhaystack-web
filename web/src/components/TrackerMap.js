// src/components/TrackerMap.js
import React, { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';

const TrackerMap = () => {
  const [locations, setLocations] = useState([]);

  const fetchData = async () => {
    try {
      const storedTrackers = JSON.parse(localStorage.getItem('tracker') || '[]');
      const response = await fetch('http://localhost:8000/api/v1/locations', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ trackers: storedTrackers }),
      });

      if (!response.ok) {
        throw new Error('Network response was not ok');
      }

      const data = await response.json();
      setLocations(data);
    } catch (error) {
      console.error('There was a problem with the fetch operation:', error.message);
    }
  };

  useEffect(() => {
    fetchData(); // Fetch data initially
    const intervalId = setInterval(fetchData, 60000); // Fetch data every 60 seconds

    return () => clearInterval(intervalId); // Clear the interval when the component is unmounted
  }, []);

  return (
    <MapContainer center={[51.505, -0.09]} zoom={13} style={{ width: '100%', height: '400px' }}>
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {locations.map((loc) => (
        <Marker key={loc.id} position={[loc.lat, loc.lng]}>
          <Popup>
            {loc.name} <br /> {new Date(loc.timestamp).toLocaleString()}
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
};

export default TrackerMap;
