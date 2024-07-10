Poncho - 3D Model Display

- Scene Setup:
Initializes the scene, camera, and renderer.

- Lighting:
Adds ambient, directional, and hemisphere lights to illuminate the model.

- Model Loading: 
Uses THREE.GLTFLoader to load the GLB file (source/Porsche.glb). 
The loader will automatically handle the textures embedded in the GLB.

- Animation Loop: 
Continuously renders the scene using requestAnimationFrame.

- Responsive Design: 
Adjusts the renderer size when the window is resized.

- Bounding Box Calculation:
After loading the model, a bounding box is calculated using THREE.Box3().setFromObject(model).

- Position Adjustment: 
The model's position is adjusted based on the bounding box's center and size to ensure its base aligns with the grid. 
The Y position of the model is set to ensure its bottom aligns with Y=0 (ground level).
