// src/components/AddTrackerForm.js
import React, { useState } from 'react';

const AddTrackerForm = () => {
  const [tracker, setTracker] = useState({
    name: '',
    key_id: '',
    private_key: '',
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    const trackers = JSON.parse(localStorage.getItem('tracker') || '[]');
    trackers.push(tracker);
    localStorage.setItem('tracker', JSON.stringify(trackers));
    setTracker({
      name: '',
      key_id: '',
      private_key: '',
    });
  };

  return (
    <form onSubmit={handleSubmit}>
      <input
        value={tracker.name}
        onChange={(e) => setTracker({ ...tracker, name: e.target.value })}
        placeholder="Name"
        required
      />
      <input
        value={tracker.key_id}
        onChange={(e) => setTracker({ ...tracker, key_id: e.target.value })}
        placeholder="Key ID"
        required
      />
      <input
        value={tracker.private_key}
        onChange={(e) => setTracker({ ...tracker, private_key: e.target.value })}
        placeholder="Private Key"
        required
      />
      <button type="submit">Add Tracker</button>
    </form>
  );
};

export default AddTrackerForm;
