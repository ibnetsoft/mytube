'use client';

import { useState, useEffect } from 'react';

interface ReferralSettings {
  referral_mode: string;
  referral_default_sponsor_uuid: string;
  referral_level1_percent: string;
  referral_level2_percent: string;
  referral_min_payout: string;
  referral_cycle: string;
}

interface User {
  id: string;
  email: string;
  user_metadata: {
    full_name?: string;
  };
  profile?: {
    referral_code?: string;
  };
}

export default function ReferralSettingsPage() {
  const [settings, setSettings] = useState<ReferralSettings>({
    referral_mode: 'NORMAL',
    referral_default_sponsor_uuid: '',
    referral_level1_percent: '10',
    referral_level2_percent: '5',
    referral_min_payout: '50',
    referral_cycle: 'MONTHLY'
  });
  
  const [users, setUsers] = useState<User[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    fetchSettings();
    fetchUsers();
  }, []);

  const fetchSettings = async () => {
    try {
      const res = await fetch('/api/admin/settings/referral');
      if (res.ok) {
        const data = await res.json();
        setSettings(prev => ({ ...prev, ...data.settings }));
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchUsers = async () => {
    try {
      const res = await fetch('/api/admin/users');
      if (res.ok) {
        const data = await res.json();
        setUsers(data.users || []);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    setMessage('');
    try {
      const res = await fetch('/api/admin/settings/referral', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
      });
      if (res.ok) {
        setMessage('Settings saved successfully.');
      } else {
        setMessage('Failed to save settings.');
      }
    } catch (e) {
      console.error(e);
      setMessage('Error occurred while saving.');
    } finally {
      setIsSaving(false);
    }
  };

  const filteredUsers = users.filter(u => {
    if (!searchQuery) return false;
    const q = searchQuery.toLowerCase();
    return u.email?.toLowerCase().includes(q) || 
           u.user_metadata?.full_name?.toLowerCase().includes(q) ||
           u.profile?.referral_code?.toLowerCase().includes(q);
  }).slice(0, 5);

  const selectedUser = users.find(u => u.id === settings.referral_default_sponsor_uuid);

  return (
    <div className="p-6 max-w-4xl mx-auto text-white">
      <h1 className="text-3xl font-bold mb-6">Referral Settings</h1>

      {message && (
        <div className="mb-4 p-3 bg-blue-900 border border-blue-500 rounded text-blue-100">
          {message}
        </div>
      )}

      <div className="space-y-6 bg-gray-800 p-6 rounded-xl border border-gray-700">
        
        {/* Referral Mode */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Referral Mode</label>
          <select 
            className="w-full bg-gray-900 border border-gray-600 rounded p-2 text-white"
            value={settings.referral_mode}
            onChange={(e) => setSettings({...settings, referral_mode: e.target.value})}
          >
            <option value="OFF">OFF</option>
            <option value="NORMAL">NORMAL</option>
            <option value="PROMOTION">PROMOTION</option>
          </select>
        </div>

        {/* Default Sponsor Selection */}
        <div className="pt-4 border-t border-gray-700">
          <label className="block text-sm font-medium text-gray-300 mb-2">Default Sponsor (Search by Email/Name/Code)</label>
          <div className="flex gap-2 mb-2">
            <input 
              type="text" 
              placeholder="Search user..."
              className="w-full bg-gray-900 border border-gray-600 rounded p-2 text-white"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          {searchQuery && (
            <div className="bg-gray-900 border border-gray-600 rounded mb-4 overflow-hidden">
              {filteredUsers.length > 0 ? filteredUsers.map(u => (
                <div 
                  key={u.id} 
                  className="p-2 hover:bg-gray-700 cursor-pointer text-sm border-b border-gray-800 last:border-0"
                  onClick={() => {
                    setSettings({...settings, referral_default_sponsor_uuid: u.id});
                    setSearchQuery('');
                  }}
                >
                  {u.user_metadata?.full_name || 'No Name'} ({u.email}) - Code: {u.profile?.referral_code || 'N/A'}
                </div>
              )) : (
                <div className="p-2 text-sm text-gray-400">No users found.</div>
              )}
            </div>
          )}
          
          <div className="p-3 bg-gray-900 border border-gray-600 rounded">
            <span className="text-gray-400 text-sm">Selected Sponsor UUID: </span>
            <span className="font-mono text-sm block mt-1">{settings.referral_default_sponsor_uuid || 'None'}</span>
            {selectedUser && (
              <span className="text-green-400 text-sm block mt-1">
                {selectedUser.user_metadata?.full_name} ({selectedUser.email})
              </span>
            )}
          </div>
        </div>

        {/* Rewards and Config */}
        <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-700">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Level 1 Reward (%)</label>
            <input 
              type="number" 
              className="w-full bg-gray-900 border border-gray-600 rounded p-2 text-white"
              value={settings.referral_level1_percent}
              onChange={(e) => setSettings({...settings, referral_level1_percent: e.target.value})}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Level 2 Reward (%)</label>
            <input 
              type="number" 
              className="w-full bg-gray-900 border border-gray-600 rounded p-2 text-white"
              value={settings.referral_level2_percent}
              onChange={(e) => setSettings({...settings, referral_level2_percent: e.target.value})}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Minimum Payout (USDT)</label>
            <input 
              type="number" 
              className="w-full bg-gray-900 border border-gray-600 rounded p-2 text-white"
              value={settings.referral_min_payout}
              onChange={(e) => setSettings({...settings, referral_min_payout: e.target.value})}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Settlement Cycle</label>
            <select 
              className="w-full bg-gray-900 border border-gray-600 rounded p-2 text-white"
              value={settings.referral_cycle}
              onChange={(e) => setSettings({...settings, referral_cycle: e.target.value})}
            >
              <option value="REALTIME">REALTIME</option>
              <option value="WEEKLY">WEEKLY</option>
              <option value="MONTHLY">MONTHLY</option>
            </select>
          </div>
        </div>

        <div className="pt-6">
          <button 
            onClick={handleSave}
            disabled={isSaving}
            className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-3 px-4 rounded transition-colors disabled:opacity-50"
          >
            {isSaving ? 'Saving...' : 'Save Referral Settings'}
          </button>
        </div>

      </div>
    </div>
  );
}
