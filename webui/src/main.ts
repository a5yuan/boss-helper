import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { initTheme } from "./ui/theme";
import "./ui/tokens/glass.css";
import "./style.css";

initTheme();
createApp(App).use(createPinia()).mount("#app");
