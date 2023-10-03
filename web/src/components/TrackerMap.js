// src/components/TrackerMap.js
import React, { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';

const TrackerMap = () => {
    const [locationsData, setLocationsData] = useState({});

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
            console.log("TrackerMap", data);
            setLocationsData(data);
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
        <MapContainer>
            <TileLayer
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            {Object.entries(locationsData).map(([trackerName, locations]) =>
                locations.map(loc => (
                    <Marker key={loc.reported_at} position={[loc.lat, loc.lng]}>
                        <Popup>
                            {trackerName} <br />
                            Accuracy: {loc.accuracy} <br />
                            {new Date(loc.reported_at * 1000).toLocaleString()}
                        </Popup>
                    </Marker>
                ))
            )}

        </MapContainer>
    );
};

export default TrackerMap;
