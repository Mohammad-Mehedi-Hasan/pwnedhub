const routes = [
    {
        path: "/signup",
        name: "signup",
        component: Signup,
    },
    {
        path: "/login",
        name: "login",
        component: Login,
    },
    {
        path: "/reset",
        name: "reset-init",
        component: ResetInit,
    },
    {
        path: "/reset/:userId/:token",
        name: "reset-password",
        component: ResetPassword,
        props: true,
    },
    {
        path: "/account",
        name: "account",
        component: Account,
        meta: {
            authRequired: true,
        },
    },
    {
        path: "/profile/:userId",
        name: "profile",
        component: Profile,
        props: true,
        meta: {
            authRequired: true,
        },
    },
    {
        path: "/notes",
        name: "notes",
        component: Notes,
        meta: {
            authRequired: true,
        },
    },
    {
        path: "/scans",
        name: "scans",
        component: Scans,
        meta: {
            authRequired: true,
        },
    },
    {
        path: "/messages",
        name: "messages",
        component: Messaging,
        meta: {
            authRequired: true,
        },
    },
    {
        path: "/mail",
        name: "mail",
        component: Mail,
        meta: {
            authRequired: true,
        },
    },
    {
        path: "/mail/view/:letterId",
        name: "letter",
        component: Letter,
        props: true,
        meta: {
            authRequired: true,
        },
    },
    {
        path: "/mail/compose",
        name: "compose",
        component: Compose,
        meta: {
            authRequired: true,
        },
    },
    {
        path: "/mail/reply/:letterId",
        name: "reply",
        component: Reply,
        props: true,
        meta: {
            authRequired: true,
        },
    },
    {
        path: "/admin/tools",
        name: "tools",
        component: Tools,
        meta: {
            authRequired: true,
        },
    },
    {
        path: "/admin/users",
        name: "users",
        component: Users,
        meta: {
            authRequired: true,
        },
    },
    {
        path: "*",
        redirect: "/messages",
    }
];

const router = new VueRouter({
    routes: routes,
});

router.beforeEach((to, from, next) => {
    if (to.matched.some(record => record.meta.authRequired)) {
        if (!store.getters.isLoggedIn) {
            next({
                name: "login",
                params: { nextUrl: to.fullPath }
            })
        } else {
            next()
        }
    } else {
        next()
    }
});
