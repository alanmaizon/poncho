import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

const TRACK_PATH = '/assets/models/racetrack_figure8.glb';
const CAR_PATH = '/assets/models/car.glb';

export interface SpawnInfo {
  position: THREE.Vector3;
  heading: number;
}

export interface TrackObjects {
  track: THREE.Group;
  walls: THREE.Mesh[];
  roadMesh: THREE.Mesh | null;
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

        const box = new THREE.Box3().setFromObject(track);
        track.position.y -= box.min.y;

        enableShadows(track);

        const extracted = extractTrackObjects(track);

        // Walls: invisible collision geometry
        for (const wall of extracted.walls) {
          wall.visible = false;
        }

        // Checkpoints & StartLine: invisible triggers
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
  roadMesh: THREE.Mesh | null;
  checkpoints: THREE.Mesh[];
  startLine: THREE.Mesh | null;
  spawn: SpawnInfo;
}

function extractTrackObjects(track: THREE.Object3D): ExtractedObjects {
  const walls: THREE.Mesh[] = [];
  const checkpoints: THREE.Mesh[] = [];
  let startLine: THREE.Mesh | null = null;
  let roadMesh: THREE.Mesh | null = null;
  let checkpoint01: THREE.Object3D | null = null;

  track.traverse((child) => {
    const mesh = child as THREE.Mesh;

    if (child.name === 'LeftWall' || child.name === 'RightWall') {
      if (mesh.isMesh) walls.push(mesh);
    }

    if (child.name === 'Road') {
      if (mesh.isMesh) roadMesh = mesh;
    }

    if (child.name.startsWith('Checkpoint_')) {
      if (mesh.isMesh) checkpoints.push(mesh);
      if (child.name === 'Checkpoint_01') checkpoint01 = child;
    }

    if (child.name === 'StartLine') {
      if (mesh.isMesh) startLine = mesh;
    }
  });

  checkpoints.sort((a, b) => a.name.localeCompare(b.name));

  const spawn = computeSpawn(startLine, checkpoint01);

  console.log(
    `Track loaded: ${walls.length} walls, road=${!!roadMesh}, ${checkpoints.length} checkpoints, startLine=${!!startLine}`
  );

  return { walls, roadMesh, checkpoints, startLine, spawn };
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

  // Keep spawn Y from the start line (may be elevated)
  startCenter.y += 0.1;
  return { position: startCenter, heading };
}

function loadCar(): Promise<THREE.Group> {
  return new Promise((resolve, reject) => {
    const loader = new GLTFLoader();
    loader.load(
      CAR_PATH,
      (gltf) => {
        const car = gltf.scene;

        const box = new THREE.Box3().setFromObject(car);
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        if (maxDim > 0) {
          const targetLength = 8;
          const scale = targetLength / maxDim;
          car.scale.multiplyScalar(scale);
        }

        const centeredBox = new THREE.Box3().setFromObject(car);
        const center = centeredBox.getCenter(new THREE.Vector3());
        car.position.x -= center.x;
        car.position.z -= center.z;
        car.position.y -= centeredBox.min.y;

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
