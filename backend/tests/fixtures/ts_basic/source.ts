import type { Value } from "value";

class Greeter {
    greet(value: Value) {
        if (value) {
            print(value);
        }
    }
}

const helper = (value: Value) => {
    if (value) {
        return value;
    }
};
