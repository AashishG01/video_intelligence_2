import axios from 'axios';
import { BACKEND_URL } from './config';

const api = axios.create({
    baseURL: BACKEND_URL,
});

// Request Interceptor: Attach the token to every request
api.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('token');
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => Promise.reject(error)
);

// Response Interceptor: Handle expired tokens globally
api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response && error.response.status === 401) {
            // Token is invalid or expired. Purge it.
            localStorage.removeItem('token');
            localStorage.removeItem('role');
            window.location.href = '/login'; // Force them to login page
        }
        return Promise.reject(error);
    }
);

export default api;