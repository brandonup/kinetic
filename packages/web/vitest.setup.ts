import "@testing-library/jest-dom";

// jsdom 27 does not implement Blob.prototype.text / arrayBuffer / stream.
// Polyfill using FileReader so that component code calling file.text() works in tests.
if (!Blob.prototype.text) {
  Object.defineProperty(Blob.prototype, "text", {
    value: function (this: Blob) {
      return new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as string);
        reader.onerror = () => reject(reader.error);
        reader.readAsText(this);
      });
    },
    writable: true,
    configurable: true,
  });
}
