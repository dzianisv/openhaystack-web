const map = L.map('map');
map.setView([0, 0], 15);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

// Tracker markers live in their own layer group so a refresh can drop exactly
// the previous set without touching the "You are here!" marker or the locate control.
const trackerLayer = L.layerGroup().addTo(map);

// Check if geolocation is available in the browser
if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(function (position) {
        const userLat = position.coords.latitude;
        const userLng = position.coords.longitude;

        map.setView([userLat, userLng], 15);

        // Add a marker for the current location
        L.marker([userLat, userLng]).addTo(map).bindPopup('You are here!').openPopup();

        // map.setZoomAround([userLat, userLng]);

        L.control.locate().addTo(map);
    }, function (error) {
        console.error("Error occurred while fetching location:", error);
    });
} else {
    console.error("Geolocation is not supported by this browser.");
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

// The REST backend is served from the same origin as this page by default.
// Override with localStorage.setItem('backendUrl', 'http://127.0.0.1:8001') when
// backend/app.py runs on another port - keep it on a loopback origin the backend
// CORS config allows (http://localhost:<port> / http://127.0.0.1:<port>).
function getBackendBaseUrl() {
    const override = localStorage.getItem('backendUrl');
    const base = override || window.location.origin;
    return base.replace(/\/+$/, '');
}

class NetworkBackend {
    async getLocations(trackers) {
        const response = await fetch(`${getBackendBaseUrl()}/api/v1/locations`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ trackers }),
        });

        if (!response.ok) {
            throw new Error(`Backend request failed: ${response.status} ${response.statusText}`);
        }

        const data = await response.json();
        localStorage.setItem('locations', JSON.stringify(data));
        return data;
    }

    static async isAvailable() {
        // Always the fallback: there is no cheap way to probe the REST backend
        // without issuing a real request, and it shares this page's origin.
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
            showError(error, 'Failed to fetch locations');
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
    trackerLayer.clearLayers();

    for (const tracker in data) {
        if (!data.hasOwnProperty(tracker)) continue; // Check if key belongs to object to avoid prototype chain issues

        // Sort positions by their unix-seconds timestamp, oldest first.
        const positions = data[tracker].slice().sort((a, b) => a.reported_at - b.reported_at);

        const iconHtml = getIconHtml(tracker);

        for (const pos of positions) {       // Create a label with the tracker name and the date-time from the timestamp
            const timestamp = formatTimestamp(pos.reported_at);
            // Create and add the marker with the custom icon to the map
            L.marker([pos.lat, pos.lng], {
                icon: L.divIcon({
                    className: 'marker',
                    html: iconHtml
                })
            }).addTo(trackerLayer).bindPopup(`${tracker}-${timestamp}`);
        }

        if (positions[positions.length - 1]) {
            addTrackerToListOnMap(tracker, iconHtml, positions[positions.length - 1]);
        }
    }
}

function addTrackerToListOnMap(trackerName, iconHtml, lastPosition) {
    console.log(trackerName, lastPosition);

    const trackerList = document.getElementById('tracker_list');

    const tracker = document.createElement("div");
    tracker.classList.add('tracker');
    tracker.innerHTML =
        iconHtml +
        `<div class="tracker-info">
            <div>${trackerName}</div>
            <div class="tracker-updated">Updated at ${formatTimestamp(lastPosition.reported_at)}</div>
            <div class="tracker-updated">Accuracy: ${lastPosition.accuracy}</div>
        </div>`;
    tracker.onclick = function () {
        map.setView([lastPosition.lat, lastPosition.lng], 15);
    };

    trackerList.appendChild(tracker);
}

function showDialog() {
    const data = localStorage.getItem('trackers');
    if (data) {
        document.getElementById('trackerTextarea').value = data;
    }
    $('#trackerModal').modal('show');
}

// Accepts an eel rejected-call object ({errorText, errorTraceback}), a native
// Error, a plain string, or null - and always renders something readable.
function describeError(error) {
    if (error === null || error === undefined) {
        return { title: 'Error', message: 'An unknown error occurred.' };
    }
    if (typeof error === 'string') {
        return { title: 'Error', message: error };
    }
    if (error.errorText || error.errorTraceback) {
        const text = error.errorText || 'Backend call failed';
        const traceback = error.errorTraceback;
        return {
            title: text.split('\n')[0].slice(0, 120),
            message: traceback ? `${text}\n\n${traceback}` : text,
        };
    }
    if (error instanceof Error || typeof error.message === 'string') {
        const text = error.message || String(error);
        return {
            title: (error.name || 'Error').slice(0, 120),
            message: error.stack ? `${text}\n\n${error.stack}` : text,
        };
    }
    try {
        return { title: 'Error', message: JSON.stringify(error) };
    } catch (e) {
        return { title: 'Error', message: String(error) };
    }
}

function showError(error, title) {
    const described = describeError(error);
    document.getElementById('errorMessage').textContent = described.message;
    document.getElementById('errorDialogTitle').textContent = title || described.title || 'Error';
    $('#errorModal').modal('show');
}

function hashCode(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = (hash << 5) - hash + char;
        hash |= 0; // Convert to 32bit integer
    }
    return hash;
}

function intToRGB(hash) {
    const r = (hash & 0xFF0000) >> 16;
    const g = (hash & 0x00FF00) >> 8;
    const b = hash & 0x0000FF;
    return `#${((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1).toUpperCase()}`;
}

function getColorFromName(name) {
    const hash = hashCode(name);
    return intToRGB(hash);
}

// Function to get the first grapheme cluster (may be a single character or an emoji)
function getFirstGraphemeCluster(str) {
    const codePoints = [...str];
    return codePoints[0];
}

function getIconHtml(name) {
    const iconColor = getColorFromName(name);
    const firstChar = getFirstGraphemeCluster(name); // Get the first grapheme cluster of the name

    return `
        <div style="width: 25px; height: 25px; border-radius: 100%; border: 1px solid #fff; background: ${iconColor}; display: flex; align-items: center; justify-content: center; font-size: 20px; font-family: 'Apple Color Emoji', 'Segoe UI Emoji', 'Noto Color Emoji', sans-serif; line-height: 1;">
            ${firstChar}
        </div>
    `;
}


fetchLocations();
setInterval(fetchLocations, 60000); // fetch every 60 seconds