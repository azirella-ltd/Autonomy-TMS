# Authorization | SAP Cloud Appliance Library

**Source**: SAP Help Portal — SAP Cloud Appliance Library > Security Considerations > Authorization

The authorization concept in SAP Cloud Appliance Library is based on user roles and access control lists (ACLs). User roles and ACLs define which objects users can access and which actions they can perform. The users and ACLs are persisted in the SAP Cloud Appliance Library database.

The authorization check is performed in the following order:

1. The system checks whether the user belongs to the SAP Cloud Appliance Library user store.
2. The system checks whether the user has permissions for the selected resource (based on ACLs).

## User Roles

### Administrator

Provides administrative permissions for performing the initial configuration of SAP Cloud Appliance Library, as well as permissions for managing users and access in SAP Cloud Appliance Library.

The administrator role also has the following permissions:

- Manage access to the accounts (assign users, change user roles and remove users)
- Edit and delete accounts
- Deactivate solutions (appliance templates)
- Remove accounts assigned to activated solutions
- Perform operations on appliances (connect and reboot)
- Perform operations on appliance backups (delete)

### Account Owner

The account owner role has the following permissions:

- Manage access to the accounts owned by you (assign users, change user roles and remove users)
- Edit or delete an account in SAP Cloud Appliance Library owned by you
- Unlock appliance templates
- Activate solutions (appliance templates)
- Deactivate solutions where you are an owner of the account for which the solution is activated
- Create and manage customized appliance templates (edit and delete)
- Create and manage appliances (activate, edit, connect, suspend, reboot, and terminate)
- Create and manage appliance backups (restore and delete)

### Account Operator

The account operator role has the following permissions in the account where the operator is assigned to:

- Create appliances by using the appliance templates activated for the SAP Cloud Appliance Library account
- Manage your appliances (activate, edit, connect, suspend, reboot, and terminate)
- Perform operations on backups for your appliances (create, restore and delete)
- Perform operations on all appliances in the account where the operator is assigned to (suspend, activate, reboot, connect, back up such appliances and restore their backups)

### Account User

The account user role has the following permissions in the account where the user is assigned to:

- Create appliances by using the appliance templates activated for the SAP Cloud Appliance Library account that the user is assigned to
- Perform operations on appliances created by the user (activate, edit, connect, suspend, reboot, terminate)
- Perform operations on backups for the appliances owned by the user (create, restore and delete)
- Perform operations on appliances created by other users (view and connect)
- Provide business users with access details for the appliances

## ACLs

In addition to the user role concept, another authorization concept is used — ACLs.

ACLs are created for both solutions and workloads. When performing an authorization check, the system searches for these ACLs.

### SAP Cloud Appliance Library ACL

The SAP Cloud Appliance Library ACL contains all registered users. This ACL distinguishes between the following users:

- **Administrators** — the permissions of these users are described in the table above (see the administrator role).
- **Users** — the permissions of these users are described in the table above (see the account owner, operator and user role).

This ACL is delivered with SAP Cloud Appliance Library. By default, it contains only the initial user of the SAP Cloud Appliance Library.

### Account ACL

The Account ACL distinguishes between the following users:

- **Account Owners** — the permissions of these users are described in the table above (see the account owner role).
- **Users** — the permissions of these users are described in the table above (see the operator and user role).

## Microsoft Azure Subscription Authorization

- **Service Principal for SAP Cloud Appliance Library** — this is the service principal that is required for the creation of SAP Cloud Appliance Library account. The required roles are:
  - Contributor
  - User Access Administrator
