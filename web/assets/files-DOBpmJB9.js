function n(r){return new Promise((o,a)=>{const e=new FileReader;e.onload=()=>o(e.result),e.onerror=a,e.readAsDataURL(r)})}export{n as f};
