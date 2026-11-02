/**
 * The signed-in user's access token never reaches the browser console: anyone who can read the
 * console (or a log or screenshot of it) could use the token as that person until it expires.
 */
import React from "react";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AppRouter from "./AppRouter";

const TOKEN = "eyJ-secret-access-token";

jest.mock("@react-keycloak/web", () => ({
  useKeycloak: () => ({
    initialized: true,
    keycloak: {
      authenticated: true,
      token: "eyJ-secret-access-token",
      tokenParsed: { realm_access: { roles: ["admin"] }, projects: [] },
    },
  }),
}));
jest.mock("../components/navbar/Navbar", () => () => null);
jest.mock("../components/landing_page/LandingPage", () => () => null);
jest.mock("../components/admin_page/AdminPage", () => () => <div>admin</div>);
jest.mock("../components/normal_user_page/NormalUserPage", () => () => <div>user</div>);
jest.mock("../components/about/About", () => () => null);

function consoleOutputWhileSignedIn() {
  const spies = ["log", "info", "debug", "warn", "error"].map((level) =>
    jest.spyOn(console, level).mockImplementation(() => {}),
  );
  render(
    <MemoryRouter initialEntries={["/app"]}>
      <AppRouter />
    </MemoryRouter>,
  );
  const output = spies.flatMap((spy) => spy.mock.calls.flat().map(String));
  spies.forEach((spy) => spy.mockRestore());
  return output;
}

test("the access token is never written to the console", () => {
  const output = consoleOutputWhileSignedIn();
  expect(output.some((line) => line.includes(TOKEN))).toBe(false);
});
