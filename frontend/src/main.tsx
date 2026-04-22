import ReactDOM from 'react-dom/client';

import { App } from './App';
import { initDashboardSentry } from './observability/sentry';
import './styles/global.css';

const rootElement = document.getElementById('root');

if (!rootElement) {
  throw new Error('Missing #root element');
}

initDashboardSentry();

ReactDOM.createRoot(rootElement).render(<App />);

