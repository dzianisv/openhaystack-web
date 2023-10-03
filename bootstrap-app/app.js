const map = L.map('map').setView([51.505, -0.09], 13);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

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

async function fetchLocations() {
    const trackers = localStorage.getItem('trackers');
    if (trackers) {
        try {
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

            drawOnMap(data);
        } catch (error) {
            showError('Network error: ' + error.message);
        }
    }
}

function drawOnMap(data) {
    for (const tracker in data) {
        const positions = data[tracker];
        const latlngs = positions.map(p => [p.lat, p.lng]);
        L.polyline(latlngs, { color: getRandomColor() }).addTo(map); // different colors for each tracker's path
        var marker = L.marker([positions[0].lat, positions[0].lng]).addTo(map);
        marker.bindPopup(tracker).openPopup();
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
