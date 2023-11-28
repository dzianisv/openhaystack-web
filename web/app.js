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

        // map.setZoomAround([userLat, userLng]);

        L.control.locate().addTo(map);
    }, function(error) {
        console.error("Error occurred while fetching location:", error);
    });
} else {
    console.error("Geolocation is not supported by this browser.");
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
        console.log("Saving trackers:", data);
        JSON.parse(data);
        localStorage.setItem('trackers', data);
        $('#trackerModal').modal('hide');
    } catch (error) {
        showError(`Invalid JSON: ${error}`);
    }
}

class NetworkBackend {
    async getLocations(trackers) {
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
    async getLocations(trackers) {
        return eel.get_locations(trackers)()
    }

    static async isAvailable() {
        return typeof eel !== 'undefined';
    }
}

async function fetchLocations() {
    const trackers = localStorage.getItem('trackers');
    const backend = await LocalBackend.isAvailable() ? new LocalBackend() : new NetworkBackend();
    console.log("Using backend:", backend.constructor.name);
    console.log("Tracker list:", trackers);

    if (trackers) {
        try {
            const locationData = await backend.getLocations(JSON.parse(trackers));
            drawOnMap(locationData);
        } catch (error) {
            showError('Network error: ' + error.message);
            console.error(error);
        }
    } else {
        console.log("No trackers found in local storage");
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
    document.getElementById('tracker_list').innerHTML = '';

    for (const tracker in data) {
        if (!data.hasOwnProperty(tracker)) continue; // Check if key belongs to object to avoid prototype chain issues

        // Sort positions based on timestamp
        const positions = data[tracker].sort((a, b) => new Date(a.reported_at) - new Date(b.reported_at));

        const iconHtml = getIconHtml();

        for (const pos of positions) {       // Create a label with the tracker name and the date-time from the timestamp
            const timestamp = formatTimestamp(pos.reported_at);
            // Create and add the marker with the custom icon to the map
            L.marker([pos.lat, pos.lng], {
                icon: L.divIcon({
                    className: 'marker',
                    html: iconHtml
                })
            }).addTo(map).bindPopup(`${tracker}-${timestamp}`).openPopup();
        }

        if (positions[positions.length - 1]) {
            addTrackerToListOnMap(tracker, iconHtml, positions[positions.length - 1]);
        }
    }
}

function addTrackerToListOnMap(trackerName, iconHtml, lastPosition) {
    const trackerList = document.getElementById('tracker_list');

    const tracker = document.createElement("div");
    tracker.classList.add('tracker');
    tracker.innerHTML =
        iconHtml +
        '<div style="padding-left: 10px;">' +
            '<div>' + trackerName + '</div>' +
            '<div style="font-size: 10px;">(Last time: ' + formatTimestamp(lastPosition.reported_at) + ')<div>' +
        '</div>';
    tracker.style.display = 'flex';
    tracker.style.alignItems = 'center';
    tracker.style.marginTop = '10px';
    tracker.style.cursor = 'pointer';
    tracker.style.background = 'rgb(51 51 51 / 15%)';
    tracker.style.padding = '4px 10px';
    tracker.style.borderRadius = '3px';
    tracker.onclick = function() {
        map.setView([lastPosition.lat, lastPosition.lng], 15);
    };

    trackerList.appendChild(tracker);
}

function getIconHtml() {
    const iconColor = getRandomColor();

    return '<div style="width: 25px; height: 25px; border-radius: 100%; border: 1px solid #fff; background: '+iconColor+'"></div>';
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