import * as THREE from 'three';

const FOLLOW_DISTANCE = 12;
const FOLLOW_HEIGHT = 5;
const LOOK_AHEAD = 4;
const SMOOTHING = 5; // higher = snappier

export class CameraController {
  private camera: THREE.PerspectiveCamera;
  private target: THREE.Object3D;
  private idealOffset = new THREE.Vector3();
  private idealLookAt = new THREE.Vector3();

  constructor(camera: THREE.PerspectiveCamera, target: THREE.Object3D) {
    this.camera = camera;
    this.target = target;
  }

  update(dt: number) {
    const heading = this.target.rotation.y;

    // Desired camera position behind the car
    this.idealOffset.set(
      -Math.sin(heading) * FOLLOW_DISTANCE,
      FOLLOW_HEIGHT,
      -Math.cos(heading) * FOLLOW_DISTANCE
    ).add(this.target.position);

    // Desired look-at point ahead of the car
    this.idealLookAt.set(
      Math.sin(heading) * LOOK_AHEAD,
      1,
      Math.cos(heading) * LOOK_AHEAD
    ).add(this.target.position);

    const t = 1 - Math.exp(-SMOOTHING * dt);
    this.camera.position.lerp(this.idealOffset, t);
    const currentLookAt = new THREE.Vector3();
    this.camera.getWorldDirection(currentLookAt);
    // Smooth look-at by lerping the target
    const smoothLookAt = new THREE.Vector3().lerpVectors(
      this.camera.position.clone().add(currentLookAt),
      this.idealLookAt,
      t
    );
    this.camera.lookAt(smoothLookAt);
  }
}
