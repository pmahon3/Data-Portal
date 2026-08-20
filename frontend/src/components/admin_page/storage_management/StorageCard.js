import React, { useState, useMemo } from 'react';
import { formatError } from '../../../utils/errorUtils';

// Subcomponent that displays a single storage instance 
export default function StorageInstanceCard({ instance: i, onDelete, onUpdate, onSync, syncing, deleting }) {
  // isEditing toggles between the storage name and input field for changing name 
  const [isEditing, setIsEditing] = useState(false);
  // editingName keeps track of user input when editing instance name
  const [editingName, setEditingName] = useState(i.name);
  // localErr handles errors specific to this card's update action 
  const [localErr, setLocalErr] = useState("");

  // Memoize the flattened config so it only recalculates if i.config changes
  const configEntries = useMemo(() => flattenConfig(i.config), [i.config]);

  async function handleSave() {
    if (!editingName.trim()) {
      setLocalErr("Instance name cannot be empty.");
      return;
    }
    setLocalErr("");
    try {
      await onUpdate(i.uuid, editingName);
      setIsEditing(false);
    } catch (err) {
      setLocalErr(formatError(err));
    }
  }

  async function handleSync() {
    if (!onSync) return;
    if (!window.confirm(`Sync storage instance "${i.name}"? Please note this process takes some time.`)) return;

    setLocalErr("");
    try {
      await onSync(i.uuid);
    } catch (err) {
      const message = formatError(err);
      setLocalErr(message);
    }
  }

  return (
    <div className="im-card">
      <div className="im-head">
        <div className="im-title">
          {isEditing ? (
            /* --- EDIT MODE UI --- */
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <input 
                type="text" 
                value={editingName} 
                onChange={e => setEditingName(e.target.value)}
                placeholder="Instance name"
                style={{ padding: '4px 6px', border: '1px solid #ccc', borderRadius: '4px' }}
              />
              <button 
                className="im-btn im-btn-primary" 
                style={{ padding: '4px 8px', fontSize: '12px' }}
                onClick={handleSave}
              >
                Save
              </button>
              <button 
                className="im-btn" 
                style={{ padding: '4px 8px', fontSize: '12px' }}
                onClick={() => {
                  setIsEditing(false);
                  setEditingName(i.name);
                  setLocalErr("");
                }}
              >
                Cancel
              </button>
            </div>
          ) : (
            /* --- DISPLAY MODE UI --- */
            <>
              <strong>{i.name}</strong>
              <button 
                title="Edit name"
                style={{ background: 'none', border: 'none', borderRadius: 8, cursor: 'pointer', padding: '0 4px', fontSize: '14px', color: '#666' }}
                onClick={() => {
                  setIsEditing(true);
                  setEditingName(i.name);
                }}
              >
                ✎
              </button>
            </>
          )}
          <span className="im-chip">{i.flavour}</span>
        </div>
        {((onSync && i.flavour === "s3") || onDelete) && (
          <div className="im-actions-right">
            {onSync && i.flavour === "s3" && (
              <button className="im-btn" disabled={syncing} onClick={handleSync}>
                {syncing ? "Syncing..." : "Sync"}
              </button>
            )}
            {onDelete && (
              <button className="im-btn im-btn-danger" disabled={deleting} onClick={() => onDelete(i)}>
                {deleting ? "Deleting..." : "Delete"}
              </button>
            )}
          </div>
        )}
      </div>

      {localErr && <div className="im-error" style={{ fontSize: '12px', marginTop: '4px' }}>{localErr}</div>}

      {/* --- CONFIGURATION DETAILS --- */}
      {i.config && configEntries.length > 0 && (
        <details className="im-details">
          <summary>Config</summary>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', paddingTop: '8px', fontSize: '14px' }}>
            
            {configEntries.map(([key, value]) => {
              const isSensitive = isSensitiveKey(key);
              const displayValue = isSensitive ? '••••••••' : String(value);

              return (
                <div key={key} style={{ display: 'flex' }}>
                  <strong style={{ minWidth: '150px', color: '#666' }}>{key}:</strong>
                  <span style={isSensitive ? { color: '#999', fontWeight: 'bold' } : {}}>
                    {displayValue}
                  </span>
                </div>
              );
            })}

          </div>
        </details>
      )}
    </div>
  );
}

// Checks if a key requires its value to be masked
const isSensitiveKey = (key) => {
  const sensitiveWords = ['secret', 'password', 'key', 'token'];
  const lowerKey = key.toLowerCase();
  return sensitiveWords.some(word => lowerKey.includes(word));
};

// Flattens the config object and filters out 'uuid'
const flattenConfig = (config) => {
  if (!config) return [];
  
  return Object.entries(config).reduce((flatList, [key, value]) => {
    if (key === 'uuid') return flatList;

    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      // Pull nested object fields to the top level
      Object.entries(value).forEach(([subKey, subValue]) => {
        flatList.push([subKey, subValue]);
      });
    } else {
      flatList.push([key, value]);
    }
    
    return flatList;
  }, []);
};
