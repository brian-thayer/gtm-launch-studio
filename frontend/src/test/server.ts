import { setupServer } from "msw/node";

/** The mock API. `setup.ts` starts it and resets it after every test; tests add handlers with `server.use`. */
export const server = setupServer();
