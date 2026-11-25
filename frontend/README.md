# OCR Invoice AI dashboard

React + TypeScript dashboard for the existing FastAPI service. The UI starts with realistic sample invoices when the API is unavailable and switches to live invoice data when it can reach the backend.

## Run locally

```powershell
cd frontend
npm install
npm run dev
```

The Vite server runs at `http://localhost:5173`, which is included in the backend's local CORS origins. Copy `.env.example` to `.env` to change `VITE_API_BASE_URL`.

The upload, list, edit, approve, and reject interactions use the existing `/invoice` API routes. Analytics visualizations use illustrative dashboard sample data because the backend does not expose aggregate monthly reporting endpoints yet.

The visual primitives in `src/components/ui.tsx` follow the project's Tailwind and shadcn-style component conventions without adding a UI-kit runtime dependency.
