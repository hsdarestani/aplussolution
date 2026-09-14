import type { CapacitorConfig } from '@capacitor/cli';
import { KeyboardResize } from '@capacitor/keyboard';

const isStaging = process.env.APP_ENV === 'staging';
const defaultAppId = isStaging ? 'de.aplussolution.staging' : 'de.aplussolution.workforce';
const defaultAppName = isStaging ? 'A+ Solution Staging' : 'A+ Solution';

const config: CapacitorConfig = {
  appId: process.env.CAPACITOR_APP_ID || defaultAppId,
  appName: process.env.CAPACITOR_APP_NAME || defaultAppName,
  webDir: 'dist',
  server: {
    androidScheme: 'https',
    iosScheme: 'https',
  },
  plugins: {
    StatusBar: { style: 'DARK' },
    Keyboard: {
      resize: KeyboardResize.Body,
      resizeOnFullScreen: true,
    },
  },
};

export default config;
