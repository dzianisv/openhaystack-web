// src/components/TrackerListDialog.js
import React from 'react';
import TrackerList from './TrackerList';

const TrackerListDialog = ({ onClose, onAdd }) => {
  return (
    <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', background: 'white', padding: '20px', zIndex: 1000 }}>
      <h2>Available Trackers</h2>
      <TrackerList />
      <button onClick={onAdd}>Add Tracker</button>
      <button onClick={onClose}>Close</button>
    </div>
  );
};

export default TrackerListDialog;
