/**
 * Electron desktop shell (optional Phase 10 sub-step b).
 *
 * Wraps the running TrackSkill AI web app in a native window. Point it at a
 * local `next start` or a deployed origin:
 *
 *   TRACKSKILL_URL=http://localhost:3000 npx electron electron/main.cjs
 *
 * One-time setup:
 *   cd apps/web
 *   npm install -D electron electron-builder
 *   # then to produce an installer:
 *   npx electron-builder --config electron-builder.json --win --publish never
 */

const { app, BrowserWindow, shell } = require("node:electron");

const TARGET = process.env.TRACKSKILL_URL || "http://localhost:3000";

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 380,
    minHeight: 520,
    title: "TrackSkill AI",
    backgroundColor: "#FAF9F6",
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  win.loadURL(TARGET);

  // External links open in the user's real browser, not a new Electron frame.
  win.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: "deny" };
  });
}

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
