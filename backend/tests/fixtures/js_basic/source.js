import value from "value";

class Greeter {
    greet(name) {
        if (name) {
            print(name);
        }
    }
}

const helper = (value) => {
    if (value) {
        return value;
    }
};
