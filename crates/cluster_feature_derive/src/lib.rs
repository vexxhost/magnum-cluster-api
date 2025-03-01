extern crate proc_macro;
use heck::ToSnakeCase;
use proc_macro::TokenStream;
use quote::quote;
use syn::{parse_macro_input, DeriveInput, Lit, Meta, NestedMeta};

#[proc_macro_derive(ClusterFeatureValues, attributes(serde))]
pub fn derive_cluster_variable_values(input: TokenStream) -> TokenStream {
    // Parse the input tokens into a syntax tree.
    let input = parse_macro_input!(input as DeriveInput);

    // Ensure we're working with a struct with named fields.
    let fields = if let syn::Data::Struct(data_struct) = &input.data {
        if let syn::Fields::Named(fields_named) = &data_struct.fields {
            &fields_named.named
        } else {
            panic!("ClusterFeatureValues can only be derived for structs with named fields");
        }
    } else {
        panic!("ClusterFeatureValues can only be derived for structs");
    };

    // Generate a variable for each field.
    let mut var_entries = Vec::new();

    for field in fields {
        let field_ident = field.ident.as_ref().unwrap();
        // Look for a serde(rename = "...") attribute on the field.
        let mut rename_value: Option<String> = None;
        for attr in &field.attrs {
            if attr.path.is_ident("serde") {
                if let Ok(Meta::List(meta_list)) = attr.parse_meta() {
                    for nested in meta_list.nested.iter() {
                        if let NestedMeta::Meta(Meta::NameValue(nv)) = nested {
                            if nv.path.is_ident("rename") {
                                if let Lit::Str(lit_str) = &nv.lit {
                                    rename_value = Some(lit_str.value());
                                }
                            }
                        }
                    }
                }
            }
        }
        // Use the rename value if present; otherwise, use the field name in snake_case.
        let var_name = match rename_value {
            Some(ref s) => s.clone(),
            None => field_ident.to_string().to_snake_case(),
        };

        let ty = &field.ty;
        var_entries.push(quote! {
            ClusterClassVariables {
                name: #var_name.into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<#ty>(),
            }
        });
    }

    // Generate the final implementation.
    let expanded = quote! {
        impl ClusterFeatureVariables for Feature {
            fn variables(&self) -> Vec<ClusterClassVariables> {
                vec![
                    #(#var_entries),*
                ]
            }
        }
    };

    TokenStream::from(expanded)
}
