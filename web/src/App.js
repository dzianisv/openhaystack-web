// src/App.js
import React from 'react';
import TrackerMap from './components/TrackerMap';
import AddTrackerForm from './components/AddTrackerForm';
import TrackerList from './components/TrackerList';

function App() {
  return (
    <div className="App">
      <AddTrackerForm />
      <TrackerList />
      <TrackerMap />
    </div>
  );
}

export default App;
