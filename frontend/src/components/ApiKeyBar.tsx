import { useState } from 'react';
import { getApiKey, setApiKey } from '../api/client';

// Lets the user paste their API key, persisted to localStorage by the client.
export function ApiKeyBar() {
  const [value, setValue] = useState(getApiKey());
  const [saved, setSaved] = useState(false);

  function save() {
    setApiKey(value);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }

  return (
    <div className="apikey-bar">
      <label htmlFor="apikey">API key</label>
      <input
        id="apikey"
        type="password"
        placeholder="sk-hearsay-..."
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <button onClick={save}>Save</button>
      {saved && <span className="saved" role="status">Saved</span>}
    </div>
  );
}
