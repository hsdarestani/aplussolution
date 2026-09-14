import type { CapacitorConfig } from '@capacitor/cli';
import { KeyboardResize } from '@capacitor/keyboard';

const isStaging = process.env.APP_ENV === 'staging';

const config: CapacitorConfig = {
  appId: isStaging ? 'de.aplussolution.staging' : 'de.aplussolution.workforce',
  appName: isStaging ? 'A+ Solution Staging' : 'A+ Solution',
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
