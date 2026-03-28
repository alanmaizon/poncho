import * as THREE from 'three';

const CAR_RADIUS = 2.0;
const PUSH_MARGIN = 0.1;
const RAY_COUNT = 12;

/**
 * Wall-mesh collision with position rollback.
 * Saves the last safe position each frame. If rays detect penetration,
 * the car is pushed out along the wall normal. If it still ends up
 * inside geometry (multiple walls / corner), it snaps back to the
 * last known safe position instead of glitching through.
 */
export class BoundarySystem {
  private car: THREE.Object3D;
  private raycaster = new THREE.Raycaster();
  private wallMeshes: THREE.Mesh[];
  private rayDirections: THREE.Vector3[] = [];
  private lastSafePos = new THREE.Vector3();
  private lastSafeHeading = 0;
  private hasSafePos = false;

  constructor(walls: THREE.Mesh[], car: THREE.Object3D) {
    this.car = car;
    this.wallMeshes = walls;

    for (const wall of walls) {
      wall.updateMatrixWorld(true);
    }

    // Radial ray directions in XZ plane
    for (let i = 0; i < RAY_COUNT; i++) {
      const angle = (i / RAY_COUNT) * Math.PI * 2;
      this.rayDirections.push(
        new THREE.Vector3(Math.sin(angle), 0, Math.cos(angle))
      );
    }
  }

  constrain(carController: { speed: number; heading: number }) {
    const pos = this.car.position;
    const origin = new THREE.Vector3(pos.x, pos.y + 0.5, pos.z);

    let collided = false;
    let totalPushX = 0;
    let totalPushZ = 0;

    // First pass: detect all wall penetrations and accumulate push vectors
    for (const dir of this.rayDirections) {
      this.raycaster.set(origin, dir);
      this.raycaster.far = CAR_RADIUS;

      const hits = this.raycaster.intersectObjects(this.wallMeshes, false);
      if (hits.length > 0) {
        const hit = hits[0];
        const penetration = CAR_RADIUS - hit.distance;

        if (penetration > 0 && hit.face) {
          collided = true;

          const normal = hit.face.normal.clone();
          normal.transformDirection(hit.object.matrixWorld);
          normal.y = 0;
          normal.normalize();

          totalPushX += normal.x * (penetration + PUSH_MARGIN);
          totalPushZ += normal.z * (penetration + PUSH_MARGIN);
        }
      }
    }

    if (collided) {
      // Apply accumulated push
      pos.x += totalPushX;
      pos.z += totalPushZ;

      // Verify we're actually clear now — re-check from pushed position
      const verifyOrigin = new THREE.Vector3(pos.x, pos.y + 0.5, pos.z);
      let stillInside = false;
      for (const dir of this.rayDirections) {
        this.raycaster.set(verifyOrigin, dir);
        this.raycaster.far = CAR_RADIUS * 0.8;
        const hits = this.raycaster.intersectObjects(this.wallMeshes, false);
        if (hits.length > 0 && hits[0].distance < CAR_RADIUS * 0.5) {
          stillInside = true;
          break;
        }
      }

      if (stillInside && this.hasSafePos) {
        // Push didn't work (corner / wedge) — rollback to last safe position
        pos.copy(this.lastSafePos);
        carController.heading = this.lastSafeHeading;
        carController.speed = 0;
      } else {
        // Push worked — dampen speed based on how hard the hit was
        const pushMag = Math.sqrt(totalPushX * totalPushX + totalPushZ * totalPushZ);
        if (pushMag > 0.3) {
          carController.speed *= 0.1; // hard hit
        } else {
          carController.speed *= 0.7; // scrape
        }
      }
    } else {
      // No collision — save as safe position
      this.lastSafePos.copy(pos);
      this.lastSafeHeading = carController.heading;
      this.hasSafePos = true;
    }

    pos.y = Math.max(pos.y, 0);
  }
}
