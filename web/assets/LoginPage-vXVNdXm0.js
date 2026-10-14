// LexBharat: the original Google/phone login screen is replaced by the invite-only sign-in page.
const r=()=>{const t=new URLSearchParams(location.search).get("redirect");location.replace("/signin"+(t&&t.startsWith("/")&&!t.startsWith("//")?"?redirect="+encodeURIComponent(t):""));return null};export{r as default};
