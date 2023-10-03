// src/components/TrackerList.js
import React, { useState, useEffect } from 'react';

const TrackerList = () => {
  const [trackers, setTrackers] = useState([]);

  useEffect(() => {
    const storedTrackers = JSON.parse(localStorage.getItem('tracker') || '[]');
    setTrackers(storedTrackers);
  }, []);

  const handleDelete = (index) => {
    const updatedTrackers = [...trackers];
    updatedTrackers.splice(index, 1);
    setTrackers(updatedTrackers);
    localStorage.setItem('tracker', JSON.stringify(updatedTrackers));
  };

  return (
    <div>
      {trackers.map((tracker, index) => (
        <div key={index}>
          <span>{tracker.name}</span>
          <button onClick={() => handleDelete(index)}>Delete</button>
        </div>
      ))}
    </div>
  );
};

export default TrackerList;
