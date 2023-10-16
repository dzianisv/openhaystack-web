const map = L.map('map');

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

// Check if geolocation is available in the browser
if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(function(position) {
        const userLat = position.coords.latitude;
        const userLng = position.coords.longitude;

        map.setView([userLat, userLng], 15);

        // Add a marker for the current location
        L.marker([userLat, userLng]).addTo(map).bindPopup('You are here!').openPopup();

        map.setZoomAround([userLat, userLng]);
    }, function(error) {
        console.log("Error occurred while fetching location:", error);
    });
} else {
    console.log("Geolocation is not supported by this browser.");
}

function showDialog() {
    const data = localStorage.getItem('trackers');
    if (data) {
        document.getElementById('trackerTextarea').value = data;
    }
    $('#trackerModal').modal('show');
}

async function saveTrackers() {
    const data = document.getElementById('trackerTextarea').value;
    try {
        JSON.parse(data);
        localStorage.setItem('trackers', data);
        $('#trackerModal').modal('hide');
    } catch (error) {
        showError(`Invalid JSON: ${error}`);
    }
}

class NetworkBackend {
    async getLocations() {
        const response = await fetch('http://localhost:8000/api/v1/locations', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({trackers: JSON.parse(trackers)}),
        });

        if (!response.ok) {
            throw new Error('Network response was not ok');
        }

        const data = await response.json();
        localStorage.setItem('locations', JSON.stringify(data));
        return data;
    }

    static async isAvailable() {
        return true;
    }
}

class LocalBackend {
    async getLocations() {
        return eel.get_locations()()
    }

    static async isAvailable() {
        return typeof eel !== 'undefined';
    }
}

async function fetchLocations() {
    const trackers = localStorage.getItem('trackers');
    const backend = await LocalBackend.isAvailable() ? new LocalBackend() : new NetworkBackend();

    if (trackers) {
        try {
            const backend = await backend.getLocations();
            drawOnMap(data);
        } catch (error) {
            showError('Network error: ' + error.message);
        }
    }
}

function formatTimestamp(timestamp) {
    // Extract year, month, day, hour, and minute
    const d = new Date(timestamp * 1000);
    const year = d.getFullYear();
    const month = ('0' + (d.getMonth() + 1)).slice(-2); // Months are 0-based in JS
    const day = ('0' + d.getDate()).slice(-2);
    const hour = ('0' + d.getHours()).slice(-2);
    const minute = ('0' + d.getMinutes()).slice(-2);

    // Construct the formatted string
    return `${year}-${month}-${day} ${hour}:${minute}`;
}

function drawOnMap(data) {
    for (const tracker in data) {
        if (!data.hasOwnProperty(tracker)) continue; // Check if key belongs to object to avoid prototype chain issues

        // Sort positions based on timestamp
        const positions = data[tracker].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

        for (const pos of positions) {       // Create a label with the tracker name and the date-time from the timestamp
            const timestamp = formatTimestamp(pos.reported_at);
            // Create and add the marker with the custom icon to the map
            L.marker([pos.lat, pos.lng]).addTo(map).bindPopup(`${tracker}-${timestamp}`).openPopup();
        }
    }
}

function getRandomColor() {
    const letters = '0123456789ABCDEF';
    let color = '#';
    for (let i = 0; i < 6; i++) {
        color += letters[Math.floor(Math.random() * 16)];
    }
    return color;
}

function showError(message) {
    document.getElementById('errorMessage').textContent = message;
    $('#errorModal').modal('show');
}

fetchLocations();
setInterval(fetchLocations, 60000); // fetch every 60 seconds
