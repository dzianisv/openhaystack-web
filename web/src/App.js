// src/App.js
import React, { useState } from 'react';
import TrackerMap from './components/TrackerMap';
import TrackerListDialog from './components/TrackerListDialog';
import AddTrackerDialog from './components/AddTrackerDialog';

function App() {
  const [isTrackerListVisible, setTrackerListVisible] = useState(false);
  const [isAddTrackerVisible, setAddTrackerVisible] = useState(false);

  return (
    <div className="App">
      <button onClick={() => setTrackerListVisible(true)}>Trackers</button>
      {isTrackerListVisible && (
        <TrackerListDialog onClose={() => setTrackerListVisible(false)} onAdd={() => setAddTrackerVisible(true)} />
      )}
      {isAddTrackerVisible && (
        <AddTrackerDialog onClose={() => setAddTrackerVisible(false)} />
      )}
      <TrackerMap />
    </div>
  );
}

export default App;
