type Widget = string;
interface Options { enabled: boolean }
function render(value: Widget, options?: Options): string {
  return value;
}