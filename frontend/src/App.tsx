/* Architecture note:
 * `App` composes the auth shell and the authenticated dashboard entrypoint.
 * Auth session ownership stays outside dashboard feature modules.
 */

import { AuthProvider } from './features/auth/AuthProvider';
import { AuthEntryPoint } from './features/auth/AuthEntryPoint';

export function App() {
  return (
    <AuthProvider>
      <AuthEntryPoint />
    </AuthProvider>
  );
}
