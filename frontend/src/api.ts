const API=(import.meta.env.VITE_API_URL||'http://localhost:8000/api').replace(/\/$/,'');
export type User={id:string;email:string;name:string;first_name:string;last_name:string;role:'admin'|'manager'|'worker'|'client';phone:string};
const token=()=>localStorage.getItem('access')||'';
export async function api<T=any>(path:string,options:RequestInit={}):Promise<T>{const isForm=options.body instanceof FormData;const r=await fetch(`${API}/${path.replace(/^\//,'')}`,{...options,headers:{...(isForm?{}:{'Content-Type':'application/json'}),...(token()?{Authorization:`Bearer ${token()}`}:{}) ,...(options.headers||{})}});if(r.status===401){localStorage.removeItem('access');localStorage.removeItem('refresh');window.dispatchEvent(new Event('auth-lost'))}if(!r.ok){let m='Ein Fehler ist aufgetreten.';try{const b=await r.json();m=b.detail||JSON.stringify(b)}catch{}throw new Error(m)}return r.status===204?({} as T):r.json()}
export async function login(email:string,password:string){const d:any=await api('auth/login/',{method:'POST',body:JSON.stringify({email,password})});localStorage.setItem('access',d.access);localStorage.setItem('refresh',d.refresh);return d.user as User}
export const me=()=>api<User>('auth/me/');
export const socialUrl=(provider:'google'|'apple')=>`${API}/auth/oauth/${provider}/start/?target=${encodeURIComponent(`${window.location.origin}/auth/callback`)}`;
export function consumeOAuth(){const p=new URLSearchParams(location.search),a=p.get('access'),r=p.get('refresh');if(a&&r){localStorage.setItem('access',a);localStorage.setItem('refresh',r);history.replaceState({},'', '/');return true}return false}
export function logout(){localStorage.clear();location.href='/'}
