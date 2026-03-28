# Poncho — 3D Driving Prototype

A lightweight browser-based 3D driving prototype built with Three.js, TypeScript, and Vite.

## Quick Start

```bash
npm install
npm run dev
```

Opens at `http://localhost:5173`.

## Controls

| Key | Action |
|---|---|
| W / ↑ | Accelerate forward |
| S / ↓ | Reverse |
| A / ← | Steer left |
| D / → | Steer right |
| Space | Brake |

## Asset Paths

Place your models in the `public/` folder:

```
public/
  assets/
    models/
      racetrack_proto.fbx   ← FBX racetrack environment
      car.glb               ← GLB player car
```

## Project Structure

```
src/
  main.ts       — App bootstrap and game loop
  scene.ts      — Renderer, lighting, ground plane
  assets.ts     — FBX/GLTF asset loading and normalization
  input.ts      — Keyboard state tracker
  car.ts        — Arcade car physics controller
  camera.ts     — Third-person follow camera
  boundary.ts   — Circular boundary constraint
  hud.ts        — Debug HUD (speed, position, heading)
```

## Build

```bash
npm run build     # Type-check + production build → dist/
npm run preview   # Serve the built output locally
```

## Notes

- The FBX track is auto-scaled to ~200 units across and centered at origin.
- The GLB car is auto-scaled to ~4 units long.
- Boundary is a circular constraint derived from the track's bounding box. Replace with mesh collision for tighter bounds.
- Car physics are pure arcade — no rigid body simulation. Tweak constants in `src/car.ts`.
