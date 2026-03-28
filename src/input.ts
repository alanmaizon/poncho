/** Simple keyboard state tracker */
class InputState {
  private keys = new Set<string>();

  constructor() {
    window.addEventListener('keydown', (e) => {
      this.keys.add(e.code);
      // prevent page scroll on arrow keys / space
      if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space'].includes(e.code)) {
        e.preventDefault();
      }
    });
    window.addEventListener('keyup', (e) => this.keys.delete(e.code));
    window.addEventListener('blur', () => this.keys.clear());
  }

  pressed(code: string): boolean {
    return this.keys.has(code);
  }

  get forward(): boolean {
    return this.pressed('KeyW') || this.pressed('ArrowUp');
  }
  get reverse(): boolean {
    return this.pressed('KeyS') || this.pressed('ArrowDown');
  }
  get left(): boolean {
    return this.pressed('KeyA') || this.pressed('ArrowLeft');
  }
  get right(): boolean {
    return this.pressed('KeyD') || this.pressed('ArrowRight');
  }
  get brake(): boolean {
    return this.pressed('Space');
  }
}

export const input = new InputState();
