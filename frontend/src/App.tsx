/* Architecture note:
 * `App` composes the auth shell and the authenticated dashboard entrypoint.
 * Auth session ownership stays outside dashboard feature modules.
 */

import { AuthProvider } from './features/auth/AuthProvider';
import { AuthEntryPoint } from './features/auth/AuthEntryPoint';
import { ThemeProvider } from './features/theme/ThemeProvider';

export function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <AuthEntryPoint />
      </AuthProvider>
    </ThemeProvider>
  );
}
