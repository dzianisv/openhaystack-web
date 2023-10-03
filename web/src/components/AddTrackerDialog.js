// src/components/AddTrackerDialog.js
import React from 'react';
import AddTrackerForm from './AddTrackerForm';

const AddTrackerDialog = ({ onClose }) => {
  return (
    <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', background: 'white', padding: '20px', zIndex: 1000 }}>
      <h2>Add New Tracker</h2>
      <AddTrackerForm />
      <button onClick={onClose}>Close</button>
    </div>
  );
};

export default AddTrackerDialog;
