import { initRenderer } from './scene';
import { loadAssets } from './assets';
import { CarController } from './car';
import { CameraController } from './camera';
import { updateHud } from './hud';
import { BoundarySystem } from './boundary';
import * as THREE from 'three';

async function main() {
  const { scene, renderer, camera, sun } = initRenderer();

  const { track, car, walls, checkpoints, startLine, spawn } =
    await loadAssets(scene);

  const carController = new CarController(car, spawn.heading);
  const cameraController = new CameraController(camera, car);
  const boundary = new BoundarySystem(walls, car);

  const timer = new THREE.Timer();

  function loop(timestamp: number) {
    requestAnimationFrame(loop);
    timer.update(timestamp);
    const dt = Math.min(timer.getDelta(), 0.05);

    carController.update(dt);
    boundary.constrain(carController);
    cameraController.update(dt);
    updateHud(carController);

    // Keep shadow camera centered on the car for crisp nearby shadows
    sun.target.position.copy(car.position);
    sun.target.updateMatrixWorld();
    sun.position.set(
      car.position.x + 60,
      100,
      car.position.z + 40
    );

    renderer.render(scene, camera);
  }

  requestAnimationFrame(loop);
}

main().catch((err) => {
  console.error('Failed to start:', err);
  document.body.innerHTML = `<pre style="color:red;padding:2em">${err}</pre>`;
});
