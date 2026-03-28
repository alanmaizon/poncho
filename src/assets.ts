import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

const TRACK_PATH = '/assets/models/racetrack_arcade_big.glb';
const CAR_PATH = '/assets/models/car.glb';

export interface SpawnInfo {
  position: THREE.Vector3;
  heading: number;
}

export interface TrackObjects {
  track: THREE.Group;
  walls: THREE.Mesh[];
  checkpoints: THREE.Mesh[];
  startLine: THREE.Mesh | null;
  spawn: SpawnInfo;
}

function enableShadows(obj: THREE.Object3D) {
  obj.traverse((child) => {
    if ((child as THREE.Mesh).isMesh) {
      child.castShadow = true;
      child.receiveShadow = true;
    }
  });
}

export async function loadAssets(scene: THREE.Scene) {
  const [trackObjects, carWrapper] = await Promise.all([loadTrack(), loadCar()]);

  scene.add(trackObjects.track);
  scene.add(carWrapper);

  // Place car at the start line
  carWrapper.position.copy(trackObjects.spawn.position);
  carWrapper.rotation.y = trackObjects.spawn.heading;

  return { ...trackObjects, car: carWrapper };
}

function loadTrack(): Promise<TrackObjects> {
  return new Promise((resolve, reject) => {
    const loader = new GLTFLoader();
    loader.load(
      TRACK_PATH,
      (gltf) => {
        const track = gltf.scene;

        // Sit on y=0
        const box = new THREE.Box3().setFromObject(track);
        track.position.y -= box.min.y;

        enableShadows(track);

        // Extract named objects
        const extracted = extractTrackObjects(track);

        // Walls: invisible, collision-only
        for (const wall of extracted.walls) {
          wall.visible = false;
        }

        // Checkpoints & StartLine: invisible, used as triggers not geometry
        for (const cp of extracted.checkpoints) {
          cp.visible = false;
        }
        if (extracted.startLine) {
          extracted.startLine.visible = false;
        }

        resolve({ track, ...extracted });
      },
      undefined,
      reject
    );
  });
}

interface ExtractedObjects {
  walls: THREE.Mesh[];
  checkpoints: THREE.Mesh[];
  startLine: THREE.Mesh | null;
  spawn: SpawnInfo;
}

function extractTrackObjects(track: THREE.Object3D): ExtractedObjects {
  const walls: THREE.Mesh[] = [];
  const checkpoints: THREE.Mesh[] = [];
  let startLine: THREE.Mesh | null = null;
  let checkpoint01: THREE.Object3D | null = null;

  track.traverse((child) => {
    const mesh = child as THREE.Mesh;

    if (child.name === 'LeftWall' || child.name === 'RightWall') {
      if (mesh.isMesh) walls.push(mesh);
    }

    if (child.name.startsWith('Checkpoint_')) {
      if (mesh.isMesh) checkpoints.push(mesh);
      if (child.name === 'Checkpoint_01') checkpoint01 = child;
    }

    if (child.name === 'StartLine') {
      if (mesh.isMesh) startLine = mesh;
    }
  });

  // Sort checkpoints by name so they're in order
  checkpoints.sort((a, b) => a.name.localeCompare(b.name));

  // Compute spawn from StartLine
  const spawn = computeSpawn(startLine, checkpoint01);

  console.log(
    `Track loaded: ${walls.length} walls, ${checkpoints.length} checkpoints, startLine=${!!startLine}`
  );

  return { walls, checkpoints, startLine, spawn };
}

function computeSpawn(
  startLine: THREE.Object3D | null,
  checkpoint01: THREE.Object3D | null
): SpawnInfo {
  if (!startLine) {
    return { position: new THREE.Vector3(0, 0.1, 0), heading: Math.PI };
  }

  const startBox = new THREE.Box3().setFromObject(startLine);
  const startCenter = startBox.getCenter(new THREE.Vector3());

  let heading = Math.PI;
  if (checkpoint01) {
    const cp1Box = new THREE.Box3().setFromObject(checkpoint01);
    const cp1Center = cp1Box.getCenter(new THREE.Vector3());
    heading = Math.atan2(
      cp1Center.x - startCenter.x,
      cp1Center.z - startCenter.z
    );
  }

  startCenter.y = 0.1;
  return { position: startCenter, heading };
}

function loadCar(): Promise<THREE.Group> {
  return new Promise((resolve, reject) => {
    const loader = new GLTFLoader();
    loader.load(
      CAR_PATH,
      (gltf) => {
        const car = gltf.scene;

        // Normalize car size to ~4 units long
        const box = new THREE.Box3().setFromObject(car);
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        if (maxDim > 0) {
          const targetLength = 4;
          const scale = targetLength / maxDim;
          car.scale.multiplyScalar(scale);
        }

        // Center on origin, bottom at y=0
        const centeredBox = new THREE.Box3().setFromObject(car);
        const center = centeredBox.getCenter(new THREE.Vector3());
        car.position.x -= center.x;
        car.position.z -= center.z;
        car.position.y -= centeredBox.min.y;

        // Rotate inner model 180° so front aligns with movement direction
        car.rotation.y = Math.PI;

        const wrapper = new THREE.Group();
        wrapper.add(car);

        enableShadows(wrapper);
        resolve(wrapper);
      },
      undefined,
      reject
    );
  });
}
