This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

The browser calls FastAPI directly for login and chat creation. In development it defaults to `http://127.0.0.1:8000`; if the API runs elsewhere, set `NEXT_PUBLIC_API_BASE_URL` in `apps/web/.env.local` to its browser-reachable origin (for example, `http://127.0.0.1:8001`) and restart the web server. The API's `CODE_AGENT_CORS_ORIGINS` must include the web origin (for example, `http://localhost:3000`). Authenticated requests use `Authorization: Bearer <token>`.

In production, an unset `NEXT_PUBLIC_API_BASE_URL` uses the current browser origin. `deploy/web/index.yaml` routes `/user` and `/chat` directly to the FastAPI Service. If deploying the web app without that Ingress, set `NEXT_PUBLIC_API_BASE_URL` to a browser-reachable HTTPS API origin **before building** Next.js, and allow the web origin in the API's CORS configuration.

Authentication API types come from the FastAPI user router's OpenAPI schema. After changing its request or response models, run `pnpm generate:api-types` from `apps/web` and commit the updated `src/generated/` files. The intermediate JSON stays in the ignored `node_modules/.cache` directory. This command uses `uv` for the Python export and Orval for TypeScript generation; it does not need a running API server.

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
