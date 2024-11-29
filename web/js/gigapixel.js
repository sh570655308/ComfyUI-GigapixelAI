import { app } from "../../scripts/app.js";

let gigapixel_setting;
const id = "comfy.gigapixel";
const ext = {
    name: id,
    async setup(app) {
        gigapixel_setting = app.ui.settings.addSetting({
            id,
            name: "Gigapixel AI (gigapixel.exe)",
            defaultValue: "C:\\Program Files\\Topaz Labs LLC\\Topaz Gigapixel AI\\gigapixel.exe",
            type: "string",
        });        
    },
    async beforeRegisterNodeDef(nodeType, nodeData, _app) {
        if (nodeData.name === 'GigapixelAI') {
            const ensureGigapixel = async (node) => {
                const gigapixelWidget = node.widgets.find(w => w.name === "gigapixel_exe");
                if (gigapixelWidget && gigapixelWidget.value === "") {
                    gigapixelWidget.value = gigapixel_setting.value;
                }
            }

            const onConfigure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function () {
                const r = onConfigure ? onConfigure.apply(this, arguments) : undefined;
                ensureGigapixel(this);
                return r;
            };

            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                ensureGigapixel(this);
                return r;
            };
        }
    },    
}
app.registerExtension(ext);
