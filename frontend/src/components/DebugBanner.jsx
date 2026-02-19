import React, { useEffect, useState } from 'react';
import { Badge, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './common';
import { api } from '../services/api';
import { API_BASE_URL } from '../config/api.ts';

// Small dev-only banner to display the resolved API base URL.
export default function DebugBanner() {
  const [resolved, setResolved] = useState('');
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const isProd = process.env.NODE_ENV === 'production';
    const enable = !isProd || /[?&]debug=1\b/.test(window.location.search) || localStorage.getItem('DBG_API_BANNER') === '1';
    setVisible(Boolean(enable));
    setResolved(api?.defaults?.baseURL || '');
  }, []);

  if (!visible) return null;

  const text = resolved || '(unset)';
  const hint = `Axios: ${text}\nEnv default: ${API_BASE_URL}`;

  return (
    <div className="fixed top-2 right-2 z-[2000]">
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge
              variant="outline"
              className="cursor-pointer"
              onClick={() => {
                try {
                  navigator.clipboard.writeText(text);
                } catch (_) {}
              }}
            >
              API: {text}
            </Badge>
          </TooltipTrigger>
          <TooltipContent>
            <pre className="m-0 text-xs">{hint}</pre>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  );
}
