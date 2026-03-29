import * as THREE from 'three';

export function initRenderer() {
  const scene = new THREE.Scene();

  // Sky gradient via hemisphere background
  scene.background = new THREE.Color(0x7ec8e3);
  scene.fog = new THREE.FogExp2(0x9dc8d6, 0.0012);

  const camera = new THREE.PerspectiveCamera(
    55,
    window.innerWidth / window.innerHeight,
    0.3,
    2000
  );
  camera.position.set(0, 10, 20);

  // --- Renderer ---
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    powerPreference: 'high-performance',
  });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  document.body.appendChild(renderer.domElement);

  // --- Lighting ---

  // Soft ambient fill
  const ambient = new THREE.AmbientLight(0xc9dff0, 0.4);
  scene.add(ambient);

  // Sky/ground hemisphere — warm sky, cool ground bounce
  const hemi = new THREE.HemisphereLight(0xffeeb1, 0x4a6741, 0.5);
  scene.add(hemi);

  // Main sun — warm directional, slightly angled for long shadows
  const sun = new THREE.DirectionalLight(0xfff4e0, 1.8);
  sun.position.set(60, 100, 40);
  sun.castShadow = true;
  sun.shadow.mapSize.set(4096, 4096);
  sun.shadow.camera.left = -150;
  sun.shadow.camera.right = 150;
  sun.shadow.camera.top = 150;
  sun.shadow.camera.bottom = -150;
  sun.shadow.camera.near = 1;
  sun.shadow.camera.far = 500;
  sun.shadow.bias = -0.0003;
  sun.shadow.normalBias = 0.02;
  scene.add(sun);

  // Secondary fill from the opposite side — cool, no shadows
  const fill = new THREE.DirectionalLight(0xb0c4de, 0.3);
  fill.position.set(-40, 30, -50);
  scene.add(fill);

  // Ground plane (visible beyond the track's own ground mesh)
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(4000, 4000),
    new THREE.MeshStandardMaterial({
      color: 0x3b7a3e,
      roughness: 0.95,
      metalness: 0.0,
    })
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.1;
  ground.receiveShadow = true;
  scene.add(ground);

  // Resize handling
  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  return { scene, renderer, camera, sun };
}
