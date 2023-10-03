Write a boostrap web app.
1. At top right corner place a green buton "Trackers". Display a dialog with a <textarea> that allows to edit a JSON array. This when dialog is closed, content of this <textarea> has to be store in the localStorage with key trackers. A json has to be validated. If json is not valid, show an error popup.
2. Each 60 secons query POST localhost:8000/api/v1/localtions, send 'trackers' from a localStorage as a application/json paylaod. Store results in the localStorage with a key "locations".
3. On the main page display a leaflet openstreet maps and path of the 'trackers'. 'trackers' has the following json schema:
```json
{
    "tracker name": [
        {
            "lat": 0.0,
            "lng": 0.0,
            "timestamp": 123456789
        }
}
```
4. Make this nicelly looking. Show error popups on network errors.